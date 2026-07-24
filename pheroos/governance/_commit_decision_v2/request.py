"""Command-intent-only portable request for Commit Decision v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
)

from pheroos.governance._commit_finality_v2 import CommitFinalityProjectionV2
from pheroos.governance._commit_decision_v2.common import (
    COMMIT_DECISION_REQUEST_SCHEMA_V2,
    _canonical_bytes,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)
from pheroos.governance._commit_decision_v2.enums import CommitDecisionCommandV2
from pheroos.governance._commit_decision_v2.proposals import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionOutputProposalV2,
    canonical_candidate_proposals_v2,
)
from pheroos.governance._commit_decision_v2.snapshot import (
    commit_decision_stream_ref_v2,
    commit_decision_transition_id_v2,
)


@dataclass(frozen=True, slots=True)
class CommitDecisionRequestV2:
    domain_root: str
    scope_ref: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    mutation_ref: str
    mutation_issuer_ref: str
    command: CommitDecisionCommandV2
    current_step: int
    candidate_proposals: Sequence[CommitDecisionCandidateProposalV2]
    output_proposal: CommitDecisionOutputProposalV2 | None
    finality_projection: CommitFinalityProjectionV2 | None
    restart_epoch: int | None
    stream_ref: str = ""
    transition_id: str = ""
    schema: str = COMMIT_DECISION_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    _root_field: ClassVar[str] = "request_root"

    def __post_init__(self) -> None:
        if (
            self.schema != COMMIT_DECISION_REQUEST_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("commit decision request version is unsupported")
        _require_root(self.domain_root, "commit decision request domain_root")
        for field in (
            "scope_ref",
            "protocol_ref",
            "run_ref",
            "target_ref",
            "mutation_ref",
            "mutation_issuer_ref",
        ):
            _require_text(getattr(self, field), f"commit decision request {field}")
        _require_count(self.observed_epoch, "commit decision request observed_epoch")
        _require_count(self.current_step, "commit decision request current_step")
        if type(self.command) is not CommitDecisionCommandV2:
            raise TypeError("commit decision request command is invalid")
        proposals = canonical_candidate_proposals_v2(self.candidate_proposals)
        object.__setattr__(self, "candidate_proposals", proposals)
        if (
            self.output_proposal is not None
            and type(self.output_proposal) is not CommitDecisionOutputProposalV2
        ):
            raise TypeError("commit decision request output proposal is invalid")
        if (
            self.finality_projection is not None
            and type(self.finality_projection) is not CommitFinalityProjectionV2
        ):
            raise TypeError("commit decision finality projection is invalid")
        if self.restart_epoch is not None:
            _require_count(self.restart_epoch, "commit decision restart_epoch")
        expected_stream = commit_decision_stream_ref_v2(
            self.scope_ref, self.protocol_ref, self.run_ref, self.target_ref
        )
        expected_transition = commit_decision_transition_id_v2(
            expected_stream, self.mutation_ref
        )
        if self.stream_ref not in ("", expected_stream) or self.transition_id not in (
            "",
            expected_transition,
        ):
            raise ValueError("commit decision request identity is mismatched")
        object.__setattr__(self, "stream_ref", expected_stream)
        object.__setattr__(self, "transition_id", expected_transition)
        self._validate_command_shape()
        _install_root(self, "request_root", self.request_root, "request", self._body())

    def _validate_command_shape(self) -> None:
        command = self.command
        if command is CommitDecisionCommandV2.INITIALIZE:
            valid = (
                not self.candidate_proposals
                and self.output_proposal is None
                and self.finality_projection is None
                and self.restart_epoch is None
            )
        elif command is CommitDecisionCommandV2.EVALUATE:
            valid = self.output_proposal is None and self.restart_epoch is None
        elif command is CommitDecisionCommandV2.SEAL:
            valid = (
                not self.candidate_proposals
                and self.output_proposal is not None
                and self.finality_projection is None
                and self.restart_epoch is None
            )
        elif command is CommitDecisionCommandV2.EXPLICIT_UNSEAL:
            valid = (
                not self.candidate_proposals
                and self.output_proposal is None
                and self.finality_projection is None
                and self.restart_epoch is None
            )
        else:
            valid = (
                not self.candidate_proposals
                and self.output_proposal is None
                and self.finality_projection is None
                and self.restart_epoch is not None
                and self.observed_epoch < MAX_AUTHORITY_REVISION_V2
                and self.restart_epoch == self.observed_epoch + 1
            )
        if not valid:
            raise ValueError("commit decision request command fields are invalid")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "mutation_ref": self.mutation_ref,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "command": self.command.value,
            "current_step": self.current_step,
            "candidate_proposals": [
                item.to_dict() for item in self.candidate_proposals
            ],
            "output_proposal": None
            if self.output_proposal is None
            else self.output_proposal.to_dict(),
            "finality_projection": None
            if self.finality_projection is None
            else self.finality_projection.to_dict(),
            "restart_epoch": self.restart_epoch,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionRequestV2:
        fields = frozenset(
            {
                "schema",
                "canonical_version",
                "domain_root",
                "scope_ref",
                "protocol_ref",
                "run_ref",
                "target_ref",
                "observed_epoch",
                "mutation_ref",
                "mutation_issuer_ref",
                "command",
                "current_step",
                "candidate_proposals",
                "output_proposal",
                "finality_projection",
                "restart_epoch",
                "stream_ref",
                "transition_id",
                "request_root",
            }
        )
        value = _exact_mapping(payload, fields, "commit decision request v2")
        try:
            value["command"] = CommitDecisionCommandV2(cast(str, value["command"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit decision command is unsupported") from exc
        candidate_proposals = tuple(
            CommitDecisionCandidateProposalV2.from_dict(item)
            for item in _exact_array(
                value["candidate_proposals"], "commit decision candidate proposals"
            )
        )
        output_proposal = (
            None
            if value["output_proposal"] is None
            else CommitDecisionOutputProposalV2.from_dict(value["output_proposal"])
        )
        finality_projection = (
            None
            if value["finality_projection"] is None
            else CommitFinalityProjectionV2.from_dict(value["finality_projection"])
        )
        decoded = cls(
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            observed_epoch=cast(int, value["observed_epoch"]),
            mutation_ref=cast(str, value["mutation_ref"]),
            mutation_issuer_ref=cast(str, value["mutation_issuer_ref"]),
            command=cast(CommitDecisionCommandV2, value["command"]),
            current_step=cast(int, value["current_step"]),
            candidate_proposals=candidate_proposals,
            output_proposal=output_proposal,
            finality_projection=finality_projection,
            restart_epoch=cast(int | None, value["restart_epoch"]),
            stream_ref=cast(str, value["stream_ref"]),
            transition_id=cast(str, value["transition_id"]),
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            request_root=cast(str, value["request_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit decision request v2"
        )
        return decoded


__all__ = ("CommitDecisionRequestV2",)
