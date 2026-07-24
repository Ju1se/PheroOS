"""Policy validation, deterministic projection, and Risk v2 source proof."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import NoReturn, Sequence, SupportsIndex, cast, final

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAssurance,
    RiskBandPolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _compute_root,
    _require_root,
)
from pheroos.governance._risk_policy import (
    RiskBand,
    _RISK_ORDER,
    _normalized_bindings,
    _validate_policy_binding,
)
from pheroos.governance._risk_v2.contracts import (
    RISK_GENESIS_SNAPSHOT_ROOT_V2,
    RISK_GENESIS_TRANSITION_ID_V2,
    RiskAssessmentRecordV2,
    RiskStateAdvanceRequestV2,
    RiskStateSnapshotV2,
    RiskThresholdSnapshotV2,
    risk_state_stream_ref_v2,
    risk_state_transition_id_v2,
)
from pheroos.governance._risk_v2.resources import (
    _require_bounded_text,
    _require_count,
)


_SOURCE_VERSION_V2 = "pheroos-risk-source-proof-v2"


@dataclass(frozen=True, slots=True)
class _RiskSourceBindingV2:
    domain_root: str
    scope_ref: str
    manifest_root: str
    commit_policy_root: str
    risk_policy_root: str
    profile: str
    assurance: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    advance_ref: str
    current_step: int
    parent_revision: int
    parent_epoch: int | None
    parent_transition_id: str
    parent_snapshot_root: str
    assessment_root: str
    threshold_root: str
    source_trace_roots: tuple[str, ...]
    source_context_root: str
    request_root: str

    def context_body(self) -> dict[str, object]:
        return {
            "version": _SOURCE_VERSION_V2,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "risk_policy_root": self.risk_policy_root,
            "profile": self.profile,
            "assurance": self.assurance,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "epoch": self.epoch,
            "advance_ref": self.advance_ref,
            "current_step": self.current_step,
            "parent_revision": self.parent_revision,
            "parent_epoch": self.parent_epoch,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "assessment_root": self.assessment_root,
            "threshold_root": self.threshold_root,
            "source_trace_roots": list(self.source_trace_roots),
        }


@dataclass(frozen=True, slots=True)
class _ValidatedRiskContextV2:
    manifest_root: str
    commit_policy_root: str
    risk_policy_root: str
    protocol_ref: str
    assurance: CommitAssurance
    commit_policy: CollectiveCommitPolicy


@final
class VerifiedRiskSourceV2:
    """Non-portable proof that policy validation produced one exact request."""

    __slots__ = ("_binding", "_manifest", "_request")

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedRiskSourceV2:
        raise TypeError("VerifiedRiskSourceV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedRiskSourceV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedRiskSourceV2 is immutable")

    def __copy__(self) -> VerifiedRiskSourceV2:
        _verified_source(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedRiskSourceV2:
        _verified_source(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedRiskSourceV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedRiskSourceV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedRiskSourceV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedRiskSourceV2 redacted>"

    @property
    def context_root(self) -> str:
        return _verified_source(self)[1].source_context_root


def prepare_risk_state_advance_v2(
    *,
    domain_root: str,
    scope_ref: str,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    run_ref: str,
    target_ref: str,
    epoch: int,
    advance_ref: str,
    current_step: int,
    assessment_ref: str,
    risk_band: RiskBand,
    risk_input_roots: Sequence[str],
    rationale_codes: Sequence[str],
    assessment_method: str,
    issuer_ref: str,
    issued_at_step: int,
    expires_at_step: int,
    provenance_ref: str,
    source_trace_roots: Sequence[str],
    parent_snapshot: RiskStateSnapshotV2 | None = None,
) -> tuple[RiskStateAdvanceRequestV2, VerifiedRiskSourceV2]:
    """Build one policy-derived Risk v2 request and its local source proof."""

    context = _validated_context(
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest=manifest,
        profile=profile,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=epoch,
        advance_ref=advance_ref,
        current_step=current_step,
    )
    if type(risk_band) is not RiskBand:
        raise TypeError("risk v2 band must use exact RiskBand")
    parent = _validated_parent(
        parent_snapshot,
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        risk_policy_root=context.risk_policy_root,
        profile=profile,
        assurance=context.assurance,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=epoch,
        current_step=current_step,
        risk_band=risk_band,
        issued_at_step=issued_at_step,
        expires_at_step=expires_at_step,
    )
    previous_root = "" if parent is None else parent.assessment.assessment_root
    reset_required = bool(
        parent is not None
        and (epoch != parent.epoch or risk_band is not parent.assessment.risk_band)
    )
    assessment = RiskAssessmentRecordV2(
        assessment_ref=assessment_ref,
        issuer_ref=issuer_ref,
        risk_band=risk_band,
        risk_input_roots=tuple(risk_input_roots),
        rationale_codes=tuple(rationale_codes),
        assessment_method=assessment_method,
        issued_at_step=issued_at_step,
        expires_at_step=expires_at_step,
        previous_assessment_root=previous_root,
        window_reset_required=reset_required,
        provenance_ref=provenance_ref,
        source_trace_roots=tuple(source_trace_roots),
    )
    if not assessment.issued_at_step <= current_step < assessment.expires_at_step:
        raise ValueError("risk v2 assessment is not fresh at current_step")
    band_policy = context.commit_policy.risk_bands[risk_band.value]
    if type(band_policy) is not RiskBandPolicy:
        raise TypeError("risk v2 selected band is not a RiskBandPolicy")
    threshold = _threshold_from_policy(
        assessment=assessment,
        risk_policy_root=context.risk_policy_root,
        band=band_policy,
    )
    parent_revision = 0 if parent is None else parent.revision
    parent_transition = (
        RISK_GENESIS_TRANSITION_ID_V2 if parent is None else parent.transition_id
    )
    parent_root = (
        RISK_GENESIS_SNAPSHOT_ROOT_V2 if parent is None else parent.snapshot_root
    )
    stream_ref = risk_state_stream_ref_v2(
        scope_ref,
        profile,
        context.assurance,
        context.manifest_root,
        context.commit_policy_root,
        context.risk_policy_root,
        context.protocol_ref,
        run_ref,
        target_ref,
    )
    transition_id = risk_state_transition_id_v2(stream_ref, advance_ref)
    context_binding = _RiskSourceBindingV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        risk_policy_root=context.risk_policy_root,
        profile=profile,
        assurance=context.assurance.value,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=epoch,
        advance_ref=advance_ref,
        current_step=current_step,
        parent_revision=parent_revision,
        parent_epoch=None if parent is None else parent.epoch,
        parent_transition_id=parent_transition,
        parent_snapshot_root=parent_root,
        assessment_root=assessment.assessment_root,
        threshold_root=threshold.threshold_root,
        source_trace_roots=tuple(assessment.source_trace_roots),
        source_context_root="",
        request_root="",
    )
    source_context_root = _compute_root(
        "risk-v2:source-context", context_binding.context_body()
    )
    snapshot = RiskStateSnapshotV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        risk_policy_root=context.risk_policy_root,
        profile=profile,
        assurance=context.assurance,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=epoch,
        stream_ref=stream_ref,
        transition_id=transition_id,
        advance_ref=advance_ref,
        revision=parent_revision + 1,
        current_step=current_step,
        parent_revision=parent_revision,
        parent_epoch=None if parent is None else parent.epoch,
        parent_transition_id=parent_transition,
        parent_snapshot_root=parent_root,
        assessment=assessment,
        threshold=threshold,
        source_context_root=source_context_root,
    )
    request = RiskStateAdvanceRequestV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=epoch,
        advance_ref=advance_ref,
        transition_id=transition_id,
        stream_ref=stream_ref,
        snapshot=snapshot,
    )
    return request, _issue_source(request, context_binding, manifest)


def _validated_context(
    *,
    domain_root: str,
    scope_ref: str,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    run_ref: str,
    target_ref: str,
    epoch: int,
    advance_ref: str,
    current_step: int,
) -> _ValidatedRiskContextV2:
    _require_root(domain_root, "risk source domain_root")
    for label, value in (
        ("scope_ref", scope_ref),
        ("profile", profile),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
        ("advance_ref", advance_ref),
    ):
        _require_bounded_text(value, f"risk source {label}")
    _require_count(epoch, "risk source epoch")
    _require_count(current_step, "risk source current_step")
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("risk source requires an exact scoped manifest")
    if target_ref not in {item.id for item in manifest.targets}:
        raise ValueError("risk source target is not declared by its manifest")
    commit_policy = manifest.collective_commit_policy
    if type(commit_policy) is not CollectiveCommitPolicy:
        raise ValueError("risk source manifest has no collective commit policy")
    try:
        assurance = CommitAssurance(commit_policy.assurance)
    except ValueError as exc:
        raise ValueError("risk source manifest assurance is unsupported") from exc
    manifest_root = manifest.manifest_root
    commit_policy_root = commit_policy_fingerprint(commit_policy, profile=profile)
    _require_root(manifest_root, "risk source manifest_root")
    _require_root(commit_policy_root, "risk source commit_policy_root")
    bindings = _normalized_bindings(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=manifest.id,
        run_id=run_ref,
        target=target_ref,
        epoch=epoch,
        field_name="risk v2 source",
    )
    risk_policy_root = _validate_policy_binding(commit_policy, bindings)
    return _ValidatedRiskContextV2(
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        risk_policy_root=risk_policy_root,
        protocol_ref=manifest.id,
        assurance=assurance,
        commit_policy=commit_policy,
    )


def _validated_parent(
    parent: RiskStateSnapshotV2 | None,
    **context: object,
) -> RiskStateSnapshotV2 | None:
    issued_at_step = _require_count(
        context.pop("issued_at_step"), "risk source issued_at_step"
    )
    expires_at_step = _require_count(
        context.pop("expires_at_step"), "risk source expires_at_step"
    )
    current_step = cast(int, context.pop("current_step"))
    risk_band = cast(RiskBand, context.pop("risk_band"))
    epoch = cast(int, context["epoch"])
    if expires_at_step <= issued_at_step:
        raise ValueError("risk source expiry must be after issuance")
    if parent is None:
        return None
    if type(parent) is not RiskStateSnapshotV2:
        raise TypeError("risk source parent must be exact RiskStateSnapshotV2")
    immutable = (
        "domain_root",
        "scope_ref",
        "manifest_root",
        "commit_policy_root",
        "risk_policy_root",
        "profile",
        "assurance",
        "protocol_ref",
        "run_ref",
        "target_ref",
    )
    if any(getattr(parent, name) != context[name] for name in immutable):
        raise ValueError("risk source parent context is mismatched")
    _require_parent_progression(
        parent,
        current_step=current_step,
        issued_at_step=issued_at_step,
        expires_at_step=expires_at_step,
        risk_band=risk_band,
        epoch=epoch,
    )
    return parent


def _require_parent_progression(
    parent: RiskStateSnapshotV2,
    *,
    current_step: int,
    issued_at_step: int,
    expires_at_step: int,
    risk_band: RiskBand,
    epoch: int,
) -> None:
    """Enforce the frozen temporal and monotonic parent invariants."""

    if current_step < parent.current_step:
        raise ValueError("risk source current_step cannot move backwards")
    if issued_at_step <= parent.assessment.issued_at_step:
        raise ValueError("risk reassessment must advance issued_at_step")
    if epoch < parent.epoch:
        raise ValueError("risk epoch cannot move backwards")
    if epoch == parent.epoch:
        if expires_at_step != parent.assessment.expires_at_step:
            raise ValueError("risk reassessment cannot alter frozen expiry")
        if _RISK_ORDER[risk_band] < _RISK_ORDER[parent.assessment.risk_band]:
            raise ValueError("risk band cannot decrease within an epoch")


def _threshold_from_policy(
    *,
    assessment: RiskAssessmentRecordV2,
    risk_policy_root: str,
    band: RiskBandPolicy,
) -> RiskThresholdSnapshotV2:
    return RiskThresholdSnapshotV2(
        assessment_root=assessment.assessment_root,
        risk_policy_root=risk_policy_root,
        risk_band=assessment.risk_band,
        minimum_positive_evidence=band.minimum_positive_evidence,
        maximum_counterevidence=band.maximum_counterevidence,
        maximum_counterevidence_ratio_ppm=band.maximum_counterevidence_ratio_ppm,
        minimum_support_clusters=band.minimum_support_clusters,
        minimum_support_ratio_ppm=band.minimum_support_ratio_ppm,
        minimum_source_diversity=band.minimum_source_diversity,
        minimum_margin=band.minimum_margin,
        stability_steps=band.stability_steps,
        required_challenge_categories=tuple(band.required_challenge_categories),
        minimum_assurance=CommitAssurance(band.minimum_assurance),
        publishable_outcomes=tuple(band.publishable_outcomes),
        executable_outcomes=tuple(band.executable_outcomes),
        extensions=band.extensions,
    )


def _issue_source(
    request: RiskStateAdvanceRequestV2,
    provisional: _RiskSourceBindingV2,
    manifest: ScopedProtocolManifestV2,
) -> VerifiedRiskSourceV2:
    binding = replace(
        provisional,
        source_context_root=request.snapshot.source_context_root,
        request_root=request.request_root,
    )
    if _compute_root("risk-v2:source-context", binding.context_body()) != (
        binding.source_context_root
    ):
        raise ValueError("risk source context construction is inconsistent")
    handle = object.__new__(VerifiedRiskSourceV2)
    object.__setattr__(
        handle, "_request", RiskStateAdvanceRequestV2.from_dict(request.to_dict())
    )
    object.__setattr__(handle, "_binding", binding)
    object.__setattr__(
        handle,
        "_manifest",
        ScopedProtocolManifestV2.from_dict(manifest.to_dict()),
    )
    return handle


def verify_risk_state_request_source_v2(
    request: RiskStateAdvanceRequestV2,
    *,
    source: object,
    committed_parent_snapshot: RiskStateSnapshotV2 | None,
) -> None:
    """Require exact request/source/historical-parent binding."""

    if type(request) is not RiskStateAdvanceRequestV2:
        raise TypeError("risk source verification requires exact request v2")
    source_request, binding = _verified_source(source)
    if source_request.to_dict() != request.to_dict():
        raise ValueError("risk source request is mismatched")
    expected_parent_revision = (
        0 if committed_parent_snapshot is None else committed_parent_snapshot.revision
    )
    expected_parent_epoch = (
        None if committed_parent_snapshot is None else committed_parent_snapshot.epoch
    )
    expected_parent_transition = (
        RISK_GENESIS_TRANSITION_ID_V2
        if committed_parent_snapshot is None
        else committed_parent_snapshot.transition_id
    )
    expected_parent_root = (
        RISK_GENESIS_SNAPSHOT_ROOT_V2
        if committed_parent_snapshot is None
        else committed_parent_snapshot.snapshot_root
    )
    snapshot = request.snapshot
    if (
        snapshot.parent_revision != expected_parent_revision
        or snapshot.parent_epoch != expected_parent_epoch
        or snapshot.parent_transition_id != expected_parent_transition
        or snapshot.parent_snapshot_root != expected_parent_root
        or binding.parent_revision != expected_parent_revision
        or binding.parent_epoch != expected_parent_epoch
        or binding.parent_transition_id != expected_parent_transition
        or binding.parent_snapshot_root != expected_parent_root
    ):
        raise ValueError("risk source parent is mismatched")
    expected_context = _expected_source_context_root(request)
    if (
        binding.source_context_root != expected_context
        or snapshot.source_context_root != expected_context
    ):
        raise ValueError("risk source context is mismatched")


def _expected_source_context_root(request: RiskStateAdvanceRequestV2) -> str:
    snapshot = request.snapshot
    binding = _RiskSourceBindingV2(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        risk_policy_root=snapshot.risk_policy_root,
        profile=snapshot.profile,
        assurance=snapshot.assurance.value,
        protocol_ref=snapshot.protocol_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        epoch=snapshot.epoch,
        advance_ref=snapshot.advance_ref,
        current_step=snapshot.current_step,
        parent_revision=snapshot.parent_revision,
        parent_epoch=snapshot.parent_epoch,
        parent_transition_id=snapshot.parent_transition_id,
        parent_snapshot_root=snapshot.parent_snapshot_root,
        assessment_root=snapshot.assessment.assessment_root,
        threshold_root=snapshot.threshold.threshold_root,
        source_trace_roots=tuple(snapshot.assessment.source_trace_roots),
        source_context_root="",
        request_root="",
    )
    return _compute_root("risk-v2:source-context", binding.context_body())


def _verified_source(
    value: object,
) -> tuple[RiskStateAdvanceRequestV2, _RiskSourceBindingV2]:
    if type(value) is not VerifiedRiskSourceV2:
        raise TypeError("risk source proof is invalid")
    try:
        request = object.__getattribute__(value, "_request")
        binding = object.__getattribute__(value, "_binding")
        manifest = object.__getattribute__(value, "_manifest")
    except AttributeError as exc:
        raise TypeError("risk source proof is incomplete") from exc
    if (
        type(request) is not RiskStateAdvanceRequestV2
        or type(binding) is not _RiskSourceBindingV2
        or type(manifest) is not ScopedProtocolManifestV2
    ):
        raise TypeError("risk source proof material is invalid")
    policy = manifest.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise ValueError("risk source proof manifest policy is unavailable")
    snapshot = request.snapshot
    context = _validated_context(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        manifest=manifest,
        profile=snapshot.profile,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        epoch=snapshot.epoch,
        advance_ref=snapshot.advance_ref,
        current_step=snapshot.current_step,
    )
    expected = _compute_root("risk-v2:source-context", binding.context_body())
    if (
        expected != binding.source_context_root
        or expected != snapshot.source_context_root
        or binding.request_root != request.request_root
        or context.manifest_root != snapshot.manifest_root
        or context.commit_policy_root != snapshot.commit_policy_root
        or context.risk_policy_root != snapshot.risk_policy_root
        or context.protocol_ref != snapshot.protocol_ref
        or context.assurance is not snapshot.assurance
    ):
        raise ValueError("risk source proof integrity is invalid")
    return RiskStateAdvanceRequestV2.from_dict(request.to_dict()), binding


def _verified_source_manifest_v2(value: object) -> ScopedProtocolManifestV2:
    """Return the exact detached manifest carried by a valid Risk source proof."""

    _verified_source(value)
    manifest = object.__getattribute__(value, "_manifest")
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("risk source proof manifest is invalid")
    return ScopedProtocolManifestV2.from_dict(manifest.to_dict())


__all__ = [
    "VerifiedRiskSourceV2",
    "prepare_risk_state_advance_v2",
    "verify_risk_state_request_source_v2",
]
