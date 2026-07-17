from __future__ import annotations

from collections.abc import Mapping

from pheroos.governance._commit.invariants import _require_authoritative_heads
from pheroos.governance._commit.records import (
    CandidateClaimBinding,
    CommitEvaluationContext,
    CommitEvaluationError,
    CommitEvaluationFailureKind,
    CommitReasonCode,
    _validate_commit_evaluation_context_shape,
)
from pheroos.governance._commit_state.records import (
    CommitReplayState,
    commit_replay_state_fingerprint,
)
from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
)
from pheroos.governance._risk.payloads import (
    commit_threshold_snapshot_fingerprint,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_fingerprint,
)
from pheroos.governance._risk.records import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLeaseReplayState,
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_fingerprint,
    support_lease_replay_state_fingerprint,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import (
    commit_manifest_fingerprint,
    commit_policy_fingerprint,
)
from pheroos.protocol.models import CapabilityManifest
from pheroos.protocol.validation import validate_capability_manifest


_COMMIT_CONTEXT_ISSUANCE = object()
_LEGACY_COMMIT_CONTEXTS = "legacy.commit.contexts"
_LEGACY_COMMIT_CONTEXT_CLAIMS = "legacy.commit.context_claims"


def issue_commit_evaluation_context(
    manifest: CapabilityManifest,
    *,
    context_id: str,
    profile: str,
    assurance: CommitAssurance,
    run_id: str,
    target: str,
    epoch: int,
    candidate_claims: Mapping[str, str],
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> CommitEvaluationContext:
    if type(manifest) is not CapabilityManifest:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context requires a canonical CapabilityManifest",
        )
    diagnostic_codes = tuple(
        item.code
        for item in validate_capability_manifest(manifest)
        if item.level == "error"
    )
    if diagnostic_codes:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context manifest is invalid: " + ", ".join(diagnostic_codes),
        )
    policy = manifest.protocol.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context requires an active collective commit policy",
        )
    normalized_profile = require_commit_profile(profile, "commit context profile")
    normalized_assurance = require_commit_assurance(
        assurance,
        "commit context assurance",
    )
    if normalized_profile not in COMMIT_PROFILES_BY_ASSURANCE[normalized_assurance.value]:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context profile and assurance do not match",
        )
    if policy.assurance != normalized_assurance.value:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context cannot downgrade or replace the declared assurance",
        )
    normalized_target = require_commit_text(target, "commit context target")
    if policy.target != normalized_target:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context target is not the active policy target",
        )
    normalized_run = require_commit_text(run_id, "commit context run_id")
    normalized_epoch = require_commit_step(epoch, "commit context epoch")
    current = require_commit_step(current_step, "commit context current_step")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_CONTEXT,
            "commit context issuance requires governance authority",
        )

    manifest_root = commit_manifest_fingerprint(manifest, profile=normalized_profile)
    policy_root = commit_policy_fingerprint(policy, profile=normalized_profile)
    protocol_id = manifest.protocol.id
    _require_authoritative_heads(
        policy=policy,
        profile=normalized_profile,
        assurance=normalized_assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=normalized_run,
        target=normalized_target,
        epoch=normalized_epoch,
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        replay_state=replay_state,
        support_replay_state=support_replay_state,
        current_step=current,
    )

    declared = tuple(
        candidate
        for candidate in manifest.protocol.candidates
        if candidate.target == normalized_target
    )
    if not isinstance(candidate_claims, Mapping):
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "candidate claims must be a mapping",
        )
    expected_ids = {candidate.id for candidate in declared}
    if set(candidate_claims) != expected_ids:
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "candidate claims must cover every declared target candidate exactly",
        )
    claims = tuple(
        CandidateClaimBinding(
            candidate_id=candidate.id,
            claim_fingerprint=require_commit_fingerprint(
                candidate_claims[candidate.id],
                f"candidate claim {candidate.id}",
            ),
            safe_fallback=candidate.safe_fallback,
        )
        for candidate in declared
    )
    fallback_id = policy.terminal_outcome.safe_fallback_candidate
    fallback_claim = next(
        (item for item in claims if item.candidate_id == fallback_id),
        None,
    )
    if fallback_claim is None or not fallback_claim.safe_fallback:
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "commit context does not bind the declared safe fallback",
        )
    substantive_ids = tuple(
        item.candidate_id
        for item in claims
        if item.candidate_id != fallback_id
    )
    if not substantive_ids:
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "commit context requires a substantive candidate",
        )
    expiry = min(
        risk_chain_state.expires_at_step,
        risk_assessment.expires_at_step,
        threshold_snapshot.expires_at_step,
        membership_snapshot.expires_at_step,
        membership_epoch_state.expires_at_step,
    )
    if current >= expiry:
        raise CommitEvaluationError(
            CommitReasonCode.CONTEXT_EXPIRED,
            "commit context authority inputs are no longer fresh",
        )
    context = CommitEvaluationContext(
        context_id=require_commit_text(context_id, "commit context context_id"),
        profile=normalized_profile,
        assurance=normalized_assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=normalized_run,
        target=normalized_target,
        epoch=normalized_epoch,
        candidate_claims=claims,
        substantive_candidate_ids=substantive_ids,
        fallback_candidate_id=fallback_id,
        risk_chain_state_fingerprint=risk_assessment_chain_state_fingerprint(
            risk_chain_state
        ),
        risk_assessment_fingerprint=risk_assessment_fingerprint(risk_assessment),
        risk_policy_root=risk_assessment.risk_policy_root,
        threshold_fingerprint=commit_threshold_snapshot_fingerprint(
            threshold_snapshot
        ),
        membership_snapshot_fingerprint=eligible_principal_snapshot_fingerprint(
            membership_snapshot
        ),
        membership_epoch_state_fingerprint=(
            eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        ),
        membership_root=membership_snapshot.membership_root,
        replay_state_fingerprint=commit_replay_state_fingerprint(replay_state),
        replay_receipt_root=replay_state.receipt_root,
        support_replay_state_fingerprint=(
            support_lease_replay_state_fingerprint(support_replay_state)
        ),
        support_replay_root=support_replay_state.replay_root,
        issuer_id=require_commit_text(issuer_id, "commit context issuer_id"),
        authority=authority,
        issued_at_step=current,
        expires_at_step=expiry,
        provenance=require_commit_text(provenance, "commit context provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "commit context trace_event_id",
        ),
    )
    context_fingerprint = commit_evaluation_context_fingerprint(context)
    authority_key = _commit_context_authority_key(context)
    claim_authority_key = _commit_context_claim_authority_key(context)
    claim_authority_fingerprint = _commit_context_claims_fingerprint(context)
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        existing_claims = registry.get(
            _LEGACY_COMMIT_CONTEXT_CLAIMS,
            claim_authority_key,
        )
        if (
            existing_claims is not None
            and existing_claims != claim_authority_fingerprint
        ):
            raise CommitEvaluationError(
                CommitReasonCode.CONTEXT_AUTHORITY_FORK,
                "commit candidate claims are immutable within one run target epoch",
                kind=CommitEvaluationFailureKind.SAFETY_FINDING,
                references=(existing_claims, claim_authority_fingerprint),
            )
        existing = registry.get(_LEGACY_COMMIT_CONTEXTS, authority_key)
        if existing is not None:
            existing_fingerprint, existing_context = existing
            if (
                existing_fingerprint == context_fingerprint
                and commit_evaluation_context_is_authoritative(existing_context)
            ):
                return existing_context
            raise CommitEvaluationError(
                CommitReasonCode.CONTEXT_AUTHORITY_FORK,
                "commit context authority heads already have a conflicting context",
                kind=CommitEvaluationFailureKind.SAFETY_FINDING,
                references=(existing_fingerprint, context_fingerprint),
            )
        object.__setattr__(context, "_authority_key", authority_key)
        object.__setattr__(
            context,
            "_issuance",
            (_COMMIT_CONTEXT_ISSUANCE, context_fingerprint),
        )
        registry.set(
            _LEGACY_COMMIT_CONTEXTS,
            authority_key,
            (context_fingerprint, context),
        )
        registry.set(
            _LEGACY_COMMIT_CONTEXT_CLAIMS,
            claim_authority_key,
            claim_authority_fingerprint,
        )
        return context

def commit_evaluation_context_payload(
    context: CommitEvaluationContext,
) -> dict[str, object]:
    if type(context) is not CommitEvaluationContext:
        raise GovernanceError("commit evaluation context must be canonical")
    _validate_commit_evaluation_context_shape(context)
    return {
        "assurance": context.assurance,
        "authority": context.authority,
        "candidate_claims": tuple(
            {
                "candidate_id": item.candidate_id,
                "claim_fingerprint": item.claim_fingerprint,
                "safe_fallback": item.safe_fallback,
            }
            for item in context.candidate_claims
        ),
        "commit_policy_root": context.commit_policy_root,
        "context_id": context.context_id,
        "epoch": context.epoch,
        "expires_at_step": context.expires_at_step,
        "fallback_candidate_id": context.fallback_candidate_id,
        "issued_at_step": context.issued_at_step,
        "issuer_id": context.issuer_id,
        "manifest_root": context.manifest_root,
        "membership_epoch_state_fingerprint": (
            context.membership_epoch_state_fingerprint
        ),
        "membership_root": context.membership_root,
        "membership_snapshot_fingerprint": (
            context.membership_snapshot_fingerprint
        ),
        "profile": context.profile,
        "protocol_id": context.protocol_id,
        "provenance": context.provenance,
        "replay_receipt_root": context.replay_receipt_root,
        "replay_state_fingerprint": context.replay_state_fingerprint,
        "risk_assessment_fingerprint": context.risk_assessment_fingerprint,
        "risk_chain_state_fingerprint": context.risk_chain_state_fingerprint,
        "risk_policy_root": context.risk_policy_root,
        "run_id": context.run_id,
        "substantive_candidate_ids": context.substantive_candidate_ids,
        "support_replay_root": context.support_replay_root,
        "support_replay_state_fingerprint": (
            context.support_replay_state_fingerprint
        ),
        "target": context.target,
        "threshold_fingerprint": context.threshold_fingerprint,
        "trace_event_id": context.trace_event_id,
    }

def commit_evaluation_context_fingerprint(
    context: CommitEvaluationContext,
) -> str:
    return commit_payload_fingerprint(
        commit_evaluation_context_payload(context),
        schema="pheroos-commit-evaluation-context-v1",
        profile=context.profile,
    )

def commit_evaluation_context_is_authoritative(context: object) -> bool:
    if type(context) is not CommitEvaluationContext:
        return False
    try:
        _validate_commit_evaluation_context_shape(context)
        issuance = context._issuance
        authority_key = _commit_context_authority_key(context)
        claim_authority_key = _commit_context_claim_authority_key(context)
        claim_fingerprint = _commit_context_claims_fingerprint(context)
        with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
            registered = registry.get(_LEGACY_COMMIT_CONTEXTS, authority_key)
            registered_claims = registry.get(
                _LEGACY_COMMIT_CONTEXT_CLAIMS,
                claim_authority_key,
            )
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_CONTEXT_ISSUANCE
            and issuance[1] == commit_evaluation_context_fingerprint(context)
            and context._authority_key == authority_key
            and registered is not None
            and registered[0] == issuance[1]
            and registered[1] is context
            and registered_claims == claim_fingerprint
        )
    except Exception:
        return False

def _commit_context_authority_key(context: CommitEvaluationContext) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": context.assurance,
            "commit_policy_root": context.commit_policy_root,
            "epoch": context.epoch,
            "manifest_root": context.manifest_root,
            "membership_epoch_state_fingerprint": (
                context.membership_epoch_state_fingerprint
            ),
            "membership_root": context.membership_root,
            "membership_snapshot_fingerprint": (
                context.membership_snapshot_fingerprint
            ),
            "profile": context.profile,
            "protocol_id": context.protocol_id,
            "replay_receipt_root": context.replay_receipt_root,
            "replay_state_fingerprint": context.replay_state_fingerprint,
            "risk_assessment_fingerprint": context.risk_assessment_fingerprint,
            "risk_chain_state_fingerprint": (
                context.risk_chain_state_fingerprint
            ),
            "risk_policy_root": context.risk_policy_root,
            "run_id": context.run_id,
            "support_replay_root": context.support_replay_root,
            "support_replay_state_fingerprint": (
                context.support_replay_state_fingerprint
            ),
            "target": context.target,
            "threshold_fingerprint": context.threshold_fingerprint,
        },
        schema="pheroos-commit-evaluation-context-authority-key-v1",
        profile=context.profile,
    )

def _commit_context_claim_authority_key(
    context: CommitEvaluationContext,
) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": context.assurance,
            "commit_policy_root": context.commit_policy_root,
            "epoch": context.epoch,
            "manifest_root": context.manifest_root,
            "profile": context.profile,
            "protocol_id": context.protocol_id,
            "run_id": context.run_id,
            "target": context.target,
        },
        schema="pheroos-commit-candidate-claim-authority-key-v1",
        profile=context.profile,
    )

def _commit_context_claims_fingerprint(
    context: CommitEvaluationContext,
) -> str:
    return commit_payload_fingerprint(
        {
            "candidate_claims": tuple(
                {
                    "candidate_id": item.candidate_id,
                    "claim_fingerprint": item.claim_fingerprint,
                    "safe_fallback": item.safe_fallback,
                }
                for item in context.candidate_claims
            ),
            "fallback_candidate_id": context.fallback_candidate_id,
            "substantive_candidate_ids": context.substantive_candidate_ids,
        },
        schema="pheroos-commit-candidate-claims-v1",
        profile=context.profile,
    )

_PUBLIC_MODULE = "pheroos.governance.commit"
for _public_object in (
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
    commit_evaluation_context_payload,
    issue_commit_evaluation_context,
):
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object
