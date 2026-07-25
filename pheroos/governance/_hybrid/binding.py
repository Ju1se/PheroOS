from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from pheroos.governance.attention import (
    ATTENTION_AUTHORITY_SCOPE,
    AttentionBreakdown,
    ExplorationDirective,
    attention_breakdown_fingerprint,
    attention_breakdown_is_authoritative,
    exploration_directive_fingerprint,
    exploration_directive_is_authoritative,
)
from pheroos.governance._commit.assessment import (
    CommitAssessment,
    CommitAssessmentStatus,
    candidate_commit_metrics_payload,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CommitAssurance


HYBRID_COMMIT_BINDING_PROFILE = "pheroos-hybrid-commit-binding-v1"
COMMIT_AUTHORITY_SOURCE = "optimal_commit_assessment_only"
_HYBRID_COMMIT_STEP_ISSUANCE = object()


@dataclass(frozen=True)
class HybridCommitStep:
    """Channel-separated binding of attention and Optimal Commit truth."""

    binding_profile: str
    profile: str
    assurance: CommitAssurance
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    current_step: int
    commit_authority_source: str
    attention_authority_scope: str
    attention_commit_authority: bool
    assessment_status: CommitAssessmentStatus
    leader_candidate_id: str
    unique_leader: bool
    leader_margin: int
    leader_ready_for_stability: bool
    commit_assessment_fingerprint: str
    commit_truth_root: str
    commit_metrics_root: str
    commit_context_root: str
    commit_evidence_root: str
    commit_challenge_root: str
    commit_lease_root: str
    attention_fingerprint: str
    exploration_directive_fingerprint: str
    attention_memory_root: str
    attention_replay_root: str
    attention_trace_root: str
    attention_source_step_root: str
    composition_root: str
    commit_assessment: CommitAssessment = field(repr=False, compare=False)
    attention: AttentionBreakdown = field(repr=False, compare=False)
    exploration_directive: ExplorationDirective = field(
        repr=False,
        compare=False,
    )
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_hybrid_commit_step_shape(self)


def bind_hybrid_commit_channels(
    *,
    attention: AttentionBreakdown,
    exploration_directive: ExplorationDirective,
    commit_assessment: CommitAssessment,
) -> HybridCommitStep:
    """Bind advisory attention beside the sole Optimal Commit truth source."""

    if not attention_breakdown_is_authoritative(attention):
        raise GovernanceError(
            "Hybrid Commit requires a governance-issued attention breakdown"
        )
    if not exploration_directive_is_authoritative(
        exploration_directive,
        attention=attention,
    ):
        raise GovernanceError(
            "Hybrid Commit requires a matching governance-issued exploration directive"
        )
    if not commit_assessment_is_authoritative(commit_assessment):
        raise GovernanceError(
            "Hybrid Commit requires a governance-issued CommitAssessment"
        )
    if (
        attention.protocol_id != commit_assessment.protocol_id
        or attention.target != commit_assessment.target
    ):
        raise GovernanceError(
            "Hybrid attention does not match the CommitAssessment protocol and target"
        )
    if attention.current_step != commit_assessment.evaluated_at_step:
        raise GovernanceError(
            "Hybrid attention and CommitAssessment must share the evaluation step"
        )
    attention_candidates = {
        item.candidate_id for item in attention.candidate_priorities
    }
    metric_candidates = {
        item.candidate_id for item in commit_assessment.candidate_metrics
    }
    if not metric_candidates or not metric_candidates.issubset(attention_candidates):
        raise GovernanceError(
            "Hybrid attention does not cover every assessed substantive candidate"
        )
    if (
        commit_assessment.leader_candidate_id
        and commit_assessment.leader_candidate_id not in attention_candidates
    ):
        raise GovernanceError("Hybrid attention does not cover the assessed leader")

    assessment_root = commit_assessment_fingerprint(commit_assessment)
    metrics_root = _commit_metrics_root(commit_assessment)
    attention_root = attention_breakdown_fingerprint(attention)
    directive_root = exploration_directive_fingerprint(exploration_directive)
    provisional = HybridCommitStep(
        binding_profile=HYBRID_COMMIT_BINDING_PROFILE,
        profile=commit_assessment.profile,
        assurance=commit_assessment.assurance,
        protocol_id=commit_assessment.protocol_id,
        run_id=commit_assessment.run_id,
        target=commit_assessment.target,
        epoch=commit_assessment.epoch,
        current_step=commit_assessment.evaluated_at_step,
        commit_authority_source=COMMIT_AUTHORITY_SOURCE,
        attention_authority_scope=ATTENTION_AUTHORITY_SCOPE,
        attention_commit_authority=False,
        assessment_status=commit_assessment.status,
        leader_candidate_id=commit_assessment.leader_candidate_id,
        unique_leader=commit_assessment.unique_leader,
        leader_margin=commit_assessment.leader_margin,
        leader_ready_for_stability=(commit_assessment.leader_ready_for_stability),
        commit_assessment_fingerprint=assessment_root,
        commit_truth_root=assessment_root,
        commit_metrics_root=metrics_root,
        commit_context_root=commit_assessment.context_fingerprint,
        commit_evidence_root=commit_assessment.collective_evidence_root,
        commit_challenge_root=commit_assessment.collective_challenge_root,
        commit_lease_root=commit_assessment.collective_lease_root,
        attention_fingerprint=attention_root,
        exploration_directive_fingerprint=directive_root,
        attention_memory_root=attention.memory_root,
        attention_replay_root=attention.replay_root,
        attention_trace_root=attention.trace_root,
        attention_source_step_root=attention.source_step_root,
        composition_root="sha256:" + "0" * 64,
        commit_assessment=commit_assessment,
        attention=attention,
        exploration_directive=exploration_directive,
    )
    composition_root = commit_payload_fingerprint(
        _hybrid_commit_composition_payload(provisional, include_root=False),
        schema="pheroos-hybrid-commit-composition-v1",
        profile=commit_assessment.profile,
    )
    result = _replace_composition_root(provisional, composition_root)
    object.__setattr__(
        result,
        "_issuance",
        (_HYBRID_COMMIT_STEP_ISSUANCE, hybrid_commit_step_fingerprint(result)),
    )
    return result


def hybrid_commit_step_payload(step: HybridCommitStep) -> dict[str, Any]:
    if type(step) is not HybridCommitStep:
        raise GovernanceError("Hybrid Commit step must be canonical")
    _validate_hybrid_commit_step_shape(step)
    return _hybrid_commit_composition_payload(step, include_root=True)


def hybrid_commit_step_fingerprint(step: HybridCommitStep) -> str:
    return commit_payload_fingerprint(
        hybrid_commit_step_payload(step),
        schema="pheroos-hybrid-commit-step-v1",
        profile=step.profile,
    )


def hybrid_commit_step_is_authoritative(step: object) -> bool:
    if type(step) is not HybridCommitStep:
        return False
    try:
        _validate_hybrid_commit_step_shape(step)
        issuance = step._issuance
        if not (
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _HYBRID_COMMIT_STEP_ISSUANCE
            and issuance[1] == hybrid_commit_step_fingerprint(step)
        ):
            return False
        if not commit_assessment_is_authoritative(step.commit_assessment):
            return False
        if not attention_breakdown_is_authoritative(step.attention):
            return False
        if not exploration_directive_is_authoritative(
            step.exploration_directive,
            attention=step.attention,
        ):
            return False
        if step.composition_root != commit_payload_fingerprint(
            _hybrid_commit_composition_payload(step, include_root=False),
            schema="pheroos-hybrid-commit-composition-v1",
            profile=step.profile,
        ):
            return False
        return _hybrid_fields_match_sources(step)
    except Exception:
        return False


def hybrid_commit_truth_projection(step: HybridCommitStep) -> dict[str, Any]:
    """Return the certificate-facing projection, excluding attention data."""

    if not hybrid_commit_step_is_authoritative(step):
        raise GovernanceError(
            "Hybrid commit truth projection requires an authoritative step"
        )
    return _hybrid_commit_truth_projection_unchecked(step)


def hybrid_attention_projection(step: HybridCommitStep) -> dict[str, Any]:
    """Return the exploration-facing projection, excluding commit truth."""

    if not hybrid_commit_step_is_authoritative(step):
        raise GovernanceError(
            "Hybrid attention projection requires an authoritative step"
        )
    return {
        "attention_authority_scope": step.attention_authority_scope,
        "attention_commit_authority": step.attention_commit_authority,
        "attention_fingerprint": step.attention_fingerprint,
        "exploration_directive_fingerprint": (step.exploration_directive_fingerprint),
        "attention_memory_root": step.attention_memory_root,
        "attention_replay_root": step.attention_replay_root,
        "attention_trace_root": step.attention_trace_root,
        "attention_source_step_root": step.attention_source_step_root,
    }


def _hybrid_commit_composition_payload(
    step: HybridCommitStep,
    *,
    include_root: bool,
) -> dict[str, Any]:
    payload = {
        "binding_profile": step.binding_profile,
        "commit": {
            **_hybrid_commit_truth_projection_unchecked(step),
            "commit_authority_source": step.commit_authority_source,
        },
        "attention": {
            "authority_scope": step.attention_authority_scope,
            "commit_authority": step.attention_commit_authority,
            "attention_fingerprint": step.attention_fingerprint,
            "exploration_directive_fingerprint": (
                step.exploration_directive_fingerprint
            ),
            "memory_root": step.attention_memory_root,
            "replay_root": step.attention_replay_root,
            "trace_root": step.attention_trace_root,
            "source_step_root": step.attention_source_step_root,
        },
    }
    if include_root:
        payload["composition_root"] = step.composition_root
    return payload


def _hybrid_commit_truth_projection_unchecked(
    step: HybridCommitStep,
) -> dict[str, Any]:
    return {
        "profile": step.profile,
        "assurance": step.assurance,
        "protocol_id": step.protocol_id,
        "run_id": step.run_id,
        "target": step.target,
        "epoch": step.epoch,
        "current_step": step.current_step,
        "assessment_status": step.assessment_status,
        "leader_candidate_id": step.leader_candidate_id,
        "unique_leader": step.unique_leader,
        "leader_margin": step.leader_margin,
        "leader_ready_for_stability": step.leader_ready_for_stability,
        "commit_assessment_fingerprint": step.commit_assessment_fingerprint,
        "commit_truth_root": step.commit_truth_root,
        "commit_metrics_root": step.commit_metrics_root,
        "commit_context_root": step.commit_context_root,
        "commit_evidence_root": step.commit_evidence_root,
        "commit_challenge_root": step.commit_challenge_root,
        "commit_lease_root": step.commit_lease_root,
    }


def _replace_composition_root(
    step: HybridCommitStep,
    root: str,
) -> HybridCommitStep:
    return replace(step, composition_root=root)


def _commit_metrics_root(assessment: CommitAssessment) -> str:
    return commit_payload_fingerprint(
        {
            "assessment_fingerprint": commit_assessment_fingerprint(assessment),
            "candidate_metrics": tuple(
                candidate_commit_metrics_payload(item)
                for item in assessment.candidate_metrics
            ),
        },
        schema="pheroos-optimal-commit-metrics-root-v1",
        profile=assessment.profile,
    )


def _validate_hybrid_commit_step_shape(step: HybridCommitStep) -> None:
    if step.binding_profile != HYBRID_COMMIT_BINDING_PROFILE:
        raise GovernanceError("Hybrid Commit binding profile is unsupported")
    if not isinstance(step.profile, str) or not step.profile:
        raise GovernanceError("Hybrid Commit profile is invalid")
    if type(step.assurance) is not CommitAssurance:
        raise GovernanceError("Hybrid Commit assurance is invalid")
    for name in ("protocol_id", "run_id", "target"):
        value = getattr(step, name)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise GovernanceError(f"Hybrid Commit {name} is invalid")
    for name in ("epoch", "current_step", "leader_margin"):
        value = getattr(step, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise GovernanceError(f"Hybrid Commit {name} is invalid")
    if step.commit_authority_source != COMMIT_AUTHORITY_SOURCE:
        raise GovernanceError("Hybrid Commit authority source is invalid")
    if step.attention_authority_scope != ATTENTION_AUTHORITY_SCOPE:
        raise GovernanceError("Hybrid attention authority scope must be none")
    if step.attention_commit_authority is not False:
        raise GovernanceError("Hybrid attention cannot carry commit authority")
    if type(step.assessment_status) is not CommitAssessmentStatus:
        raise GovernanceError("Hybrid Commit assessment status is invalid")
    if type(step.unique_leader) is not bool:
        raise GovernanceError("Hybrid Commit unique_leader is invalid")
    if type(step.leader_ready_for_stability) is not bool:
        raise GovernanceError("Hybrid Commit leader_ready_for_stability is invalid")
    if step.unique_leader:
        if (
            not isinstance(step.leader_candidate_id, str)
            or not step.leader_candidate_id
        ):
            raise GovernanceError("Hybrid Commit unique leader is missing")
    elif step.leader_candidate_id:
        raise GovernanceError("Hybrid Commit non-unique assessment names a leader")
    for name in (
        "commit_assessment_fingerprint",
        "commit_truth_root",
        "commit_metrics_root",
        "commit_context_root",
        "commit_evidence_root",
        "commit_challenge_root",
        "commit_lease_root",
        "attention_fingerprint",
        "exploration_directive_fingerprint",
        "attention_memory_root",
        "attention_replay_root",
        "attention_trace_root",
        "attention_source_step_root",
        "composition_root",
    ):
        _require_sha256(getattr(step, name), f"Hybrid Commit {name}")
    if step.commit_truth_root != step.commit_assessment_fingerprint:
        raise GovernanceError(
            "Hybrid Commit truth root must be the CommitAssessment fingerprint"
        )
    if type(step.commit_assessment) is not CommitAssessment:
        raise GovernanceError("Hybrid Commit assessment object is not canonical")
    if type(step.attention) is not AttentionBreakdown:
        raise GovernanceError("Hybrid Commit attention object is not canonical")
    if type(step.exploration_directive) is not ExplorationDirective:
        raise GovernanceError("Hybrid Commit directive object is not canonical")


def _hybrid_fields_match_sources(step: HybridCommitStep) -> bool:
    assessment = step.commit_assessment
    attention = step.attention
    directive = step.exploration_directive
    return bool(
        step.profile == assessment.profile
        and step.assurance == assessment.assurance
        and step.protocol_id == assessment.protocol_id == attention.protocol_id
        and step.run_id == assessment.run_id
        and step.target == assessment.target == attention.target
        and step.epoch == assessment.epoch
        and step.current_step == assessment.evaluated_at_step == attention.current_step
        and step.assessment_status == assessment.status
        and step.leader_candidate_id == assessment.leader_candidate_id
        and step.unique_leader == assessment.unique_leader
        and step.leader_margin == assessment.leader_margin
        and step.leader_ready_for_stability == assessment.leader_ready_for_stability
        and step.commit_assessment_fingerprint
        == commit_assessment_fingerprint(assessment)
        and step.commit_truth_root == commit_assessment_fingerprint(assessment)
        and step.commit_metrics_root == _commit_metrics_root(assessment)
        and step.commit_context_root == assessment.context_fingerprint
        and step.commit_evidence_root == assessment.collective_evidence_root
        and step.commit_challenge_root == assessment.collective_challenge_root
        and step.commit_lease_root == assessment.collective_lease_root
        and step.attention_fingerprint == attention_breakdown_fingerprint(attention)
        and step.exploration_directive_fingerprint
        == exploration_directive_fingerprint(directive)
        and step.attention_memory_root == attention.memory_root
        and step.attention_replay_root == attention.replay_root
        and step.attention_trace_root == attention.trace_root
        and step.attention_source_step_root == attention.source_step_root
    )


def _require_sha256(value: object, field_name: str) -> str:
    if not (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    ):
        raise GovernanceError(f"{field_name} must be a canonical sha256 fingerprint")
    return value


# The implementation has one private owner, while the stable ABI remains the
# historical public module for repr, introspection and pickle compatibility.
_PUBLIC_MODULE = "pheroos.governance.hybrid_commit"
HybridCommitStep.__module__ = _PUBLIC_MODULE
for _public_function in (
    bind_hybrid_commit_channels,
    hybrid_attention_projection,
    hybrid_commit_step_fingerprint,
    hybrid_commit_step_is_authoritative,
    hybrid_commit_step_payload,
    hybrid_commit_truth_projection,
):
    _public_function.__module__ = _PUBLIC_MODULE


__all__ = [
    "COMMIT_AUTHORITY_SOURCE",
    "HYBRID_COMMIT_BINDING_PROFILE",
    "HybridCommitStep",
    "bind_hybrid_commit_channels",
    "hybrid_attention_projection",
    "hybrid_commit_step_fingerprint",
    "hybrid_commit_step_is_authoritative",
    "hybrid_commit_step_payload",
    "hybrid_commit_truth_projection",
]
