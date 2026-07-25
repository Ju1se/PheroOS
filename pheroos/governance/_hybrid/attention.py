"""Non-authoritative attention channel binding and diagnostics."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance._hybrid.binding import (
    HybridCommitStep,
    bind_hybrid_commit_channels,
)
from pheroos.governance._hybrid.evaluation_records import (
    _ATTENTION_CHANNEL_DIAGNOSTIC_CODE as _RECORD_ATTENTION_DIAGNOSTIC_CODE,
    _ATTENTION_CHANNEL_MESSAGES,
    HybridCommitDiagnostic,
    _diagnostic,
)
from pheroos.governance._hybrid.request import (
    HybridCommitEvaluationRequest,
    _safe_fingerprint,
)
from pheroos.governance.attention import (
    AttentionBreakdown,
    ExplorationDirective,
    attention_breakdown_fingerprint,
    attention_breakdown_is_authoritative,
    exploration_directive_fingerprint,
    exploration_directive_is_authoritative,
)
from pheroos.governance.commit import CommitAssessment
from pheroos.governance.errors import GovernanceError


_ATTENTION_CHANNEL_DIAGNOSTIC_CODE = "attention_channel_unavailable"
if _ATTENTION_CHANNEL_DIAGNOSTIC_CODE != _RECORD_ATTENTION_DIAGNOSTIC_CODE:
    raise RuntimeError("Hybrid attention diagnostic contract drifted")


def _attention_channel_diagnostic(
    stage: str,
    *,
    request: object,
) -> HybridCommitDiagnostic:
    if stage not in _ATTENTION_CHANNEL_MESSAGES:
        raise GovernanceError("attention channel diagnostic stage is invalid")
    references: list[str] = []
    if type(request) is HybridCommitEvaluationRequest:
        if stage in {"attention", "channel_binding"}:
            attention_ref = _safe_fingerprint(
                request.attention,
                attention_breakdown_fingerprint,
            )
            if attention_ref:
                references.append(attention_ref)
        if stage in {"exploration_directive", "channel_binding"}:
            directive_ref = _safe_fingerprint(
                request.exploration_directive,
                exploration_directive_fingerprint,
            )
            if directive_ref:
                references.append(directive_ref)
    return _diagnostic(
        _ATTENTION_CHANNEL_DIAGNOSTIC_CODE,
        stage,
        _ATTENTION_CHANNEL_MESSAGES[stage],
        fatal=False,
        references=tuple(references),
    )


def _bind_attention_channel(
    request: HybridCommitEvaluationRequest,
    *,
    assessment: CommitAssessment,
) -> tuple[HybridCommitStep | None, HybridCommitDiagnostic | None]:
    """Bind advisory attention, quarantining every channel-local failure."""

    attention = request.attention
    if not attention_breakdown_is_authoritative(attention):
        return None, _attention_channel_diagnostic("attention", request=request)
    if type(attention) is not AttentionBreakdown:
        return None, _attention_channel_diagnostic("attention", request=request)
    directive = request.exploration_directive
    if not exploration_directive_is_authoritative(
        directive,
        attention=attention,
    ):
        return None, _attention_channel_diagnostic(
            "exploration_directive",
            request=request,
        )
    if type(directive) is not ExplorationDirective:
        return None, _attention_channel_diagnostic(
            "exploration_directive",
            request=request,
        )
    try:
        return (
            bind_hybrid_commit_channels(
                attention=attention,
                exploration_directive=directive,
                commit_assessment=assessment,
            ),
            None,
        )
    except Exception:
        # The records are independently authoritative, so the remaining
        # failure is their binding to this assessment (scope, step, or
        # candidate coverage).  Do not expose exception text or object repr.
        return None, _attention_channel_diagnostic(
            "channel_binding",
            request=request,
        )


def _with_exact_attention_channel_diagnostic(
    diagnostics: Sequence[HybridCommitDiagnostic],
    *,
    request: object,
) -> tuple[HybridCommitDiagnostic, ...]:
    retained = tuple(
        item for item in diagnostics if item.code != _ATTENTION_CHANNEL_DIAGNOSTIC_CODE
    )
    if type(request) is HybridCommitEvaluationRequest:
        attention = request.attention
        directive = request.exploration_directive
        if not attention_breakdown_is_authoritative(attention):
            stage = "attention"
        elif type(attention) is not AttentionBreakdown:
            stage = "attention"
        elif not exploration_directive_is_authoritative(
            directive,
            attention=attention,
        ):
            stage = "exploration_directive"
        else:
            stage = "channel_binding"
    else:
        stage = "channel_binding"
    return tuple(
        (
            *retained,
            _attention_channel_diagnostic(stage, request=request),
        )
    )


__all__: list[str] = []
