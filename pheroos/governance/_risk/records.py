from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._risk_policy import (
    _RISK_ORDER as _RISK_ORDER,
)
from pheroos.governance._risk_policy import (
    _RISK_ORDER_BY_VALUE,
    RiskBand as RiskBand,
    _risk_band_values,
    _validate_bound_record,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import WEIGHT_SCALE, require_scaled_integer
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    CommitAssurance,
    RiskBandPolicy,
)


@dataclass(frozen=True)
class RiskAssessmentChainState:
    chain_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    risk_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    revision: int
    latest_assessment_fingerprint: str
    latest_risk_band: str
    initialized_at_step: int
    last_issued_at_step: int
    expires_at_step: int
    previous_state_fingerprint: str
    issuer_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _cursor: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_risk_assessment_chain_state_shape(self)


@dataclass(frozen=True)
class RiskAssessment:
    assessment_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    risk_policy_root: str
    risk_chain_id: str
    risk_chain_revision: int
    previous_chain_state_fingerprint: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    risk_band: RiskBand
    risk_input_fingerprints: tuple[str, ...]
    rationale_codes: tuple[str, ...]
    assessment_method: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    previous_assessment_fingerprint: str
    window_reset_required: bool
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "risk_input_fingerprints",
            _canonical_fingerprints(
                self.risk_input_fingerprints,
                "risk assessment input fingerprints",
            ),
        )
        object.__setattr__(
            self,
            "rationale_codes",
            require_commit_labels(
                self.rationale_codes,
                "risk assessment rationale_codes",
            ),
        )
        _validate_risk_assessment_shape(self)


@dataclass(frozen=True)
class CommitThresholdSnapshot:
    threshold_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    risk_policy_root: str
    risk_chain_id: str
    risk_chain_revision: int
    risk_chain_state_fingerprint: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    risk_assessment_fingerprint: str
    risk_band: RiskBand
    minimum_positive_evidence: int
    maximum_counterevidence: int
    maximum_counterevidence_ratio_ppm: int
    minimum_support_clusters: int
    minimum_support_ratio_ppm: int
    minimum_source_diversity: int
    minimum_margin: int
    stability_steps: int
    required_challenge_categories: tuple[str, ...]
    minimum_assurance: CommitAssurance
    publishable_outcomes: tuple[str, ...]
    executable_outcomes: tuple[str, ...]
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_challenge_categories",
            require_commit_labels(
                self.required_challenge_categories,
                "commit threshold required challenge categories",
            ),
        )
        object.__setattr__(
            self,
            "publishable_outcomes",
            require_commit_labels(
                self.publishable_outcomes,
                "commit threshold publishable outcomes",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "executable_outcomes",
            require_commit_labels(
                self.executable_outcomes,
                "commit threshold executable outcomes",
                allow_empty=True,
            ),
        )
        _validate_threshold_snapshot_shape(self)


def _validate_risk_assessment_shape(assessment: RiskAssessment) -> None:
    _validate_bound_record(assessment, "risk assessment")
    revision = _validate_risk_assessment_identity(assessment)
    _validate_risk_assessment_lineage(assessment, revision=revision)
    _validate_risk_assessment_authority_window(assessment)


def _validate_risk_assessment_identity(assessment: RiskAssessment) -> int:
    for name in (
        "assessment_id",
        "assessment_method",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(getattr(assessment, name), f"risk assessment {name}")
    if type(assessment.risk_band) is not RiskBand:
        raise GovernanceError("risk assessment band is invalid")
    for name in (
        "risk_policy_root",
        "risk_chain_id",
        "previous_chain_state_fingerprint",
    ):
        require_commit_fingerprint(getattr(assessment, name), f"risk assessment {name}")
    revision = require_commit_step(
        assessment.risk_chain_revision,
        "risk assessment risk_chain_revision",
    )
    if revision <= 0:
        raise GovernanceError("risk assessment chain revision must be positive")
    return revision


def _validate_risk_assessment_lineage(
    assessment: RiskAssessment,
    *,
    revision: int,
) -> None:
    _canonical_fingerprints(
        assessment.risk_input_fingerprints,
        "risk assessment input fingerprints",
    )
    require_commit_labels(
        assessment.rationale_codes,
        "risk assessment rationale_codes",
    )
    if assessment.previous_assessment_fingerprint:
        require_commit_fingerprint(
            assessment.previous_assessment_fingerprint,
            "risk assessment previous_assessment_fingerprint",
        )
    if revision == 1 and assessment.previous_assessment_fingerprint:
        raise GovernanceError("initial risk assessment cannot name a predecessor")
    if revision > 1 and not assessment.previous_assessment_fingerprint:
        raise GovernanceError("risk reassessment must name its predecessor")
    if type(assessment.window_reset_required) is not bool:
        raise GovernanceError("risk assessment reset flag must be boolean")
    if (
        not assessment.previous_assessment_fingerprint
        and assessment.window_reset_required
    ):
        raise GovernanceError("initial risk assessment cannot require a risk reset")


def _validate_risk_assessment_authority_window(assessment: RiskAssessment) -> None:
    if type(assessment.authority) is not AuthorityLevel or not can_verify(
        assessment.authority
    ):
        raise GovernanceError("risk assessment authority is invalid")
    issued = require_commit_step(
        assessment.issued_at_step,
        "risk assessment issued_at_step",
    )
    expires = require_commit_step(
        assessment.expires_at_step,
        "risk assessment expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("risk assessment expiry must be after issuance")


def _validate_risk_assessment_chain_state_shape(
    state: RiskAssessmentChainState,
) -> None:
    _validate_bound_record(state, "risk assessment chain state")
    for name in (
        "chain_id",
        "risk_policy_root",
    ):
        require_commit_fingerprint(
            getattr(state, name),
            f"risk assessment chain state {name}",
        )
    for name in ("issuer_id", "provenance", "trace_event_id"):
        require_commit_text(
            getattr(state, name),
            f"risk assessment chain state {name}",
        )
    revision = require_commit_step(
        state.revision,
        "risk assessment chain state revision",
    )
    initialized = require_commit_step(
        state.initialized_at_step,
        "risk assessment chain state initialized_at_step",
    )
    last_issued = require_commit_step(
        state.last_issued_at_step,
        "risk assessment chain state last_issued_at_step",
    )
    expires = require_commit_step(
        state.expires_at_step,
        "risk assessment chain state expires_at_step",
    )
    if expires <= initialized:
        raise GovernanceError(
            "risk assessment chain expiry must be after initialization"
        )
    if not initialized <= last_issued < expires:
        raise GovernanceError("risk assessment chain issuance step is out of bounds")
    if type(state.authority) is not AuthorityLevel or not can_verify(state.authority):
        raise GovernanceError("risk assessment chain authority is invalid")
    if revision == 0:
        if (
            state.latest_assessment_fingerprint
            or state.latest_risk_band
            or state.previous_state_fingerprint
        ):
            raise GovernanceError("empty risk assessment chain has a forged head")
        if last_issued != initialized:
            raise GovernanceError(
                "empty risk assessment chain issuance step is invalid"
            )
    else:
        require_commit_fingerprint(
            state.latest_assessment_fingerprint,
            "risk assessment chain latest_assessment_fingerprint",
        )
        require_commit_fingerprint(
            state.previous_state_fingerprint,
            "risk assessment chain previous_state_fingerprint",
        )
        if state.latest_risk_band not in _RISK_ORDER_BY_VALUE:
            raise GovernanceError("risk assessment chain latest risk band is invalid")


def _validate_threshold_snapshot_shape(snapshot: CommitThresholdSnapshot) -> None:
    _validate_bound_record(snapshot, "commit threshold")
    _validate_threshold_identity(snapshot)
    _validate_threshold_numeric_bounds(snapshot)
    _validate_threshold_labels(snapshot)
    _validate_threshold_authority_window(snapshot)


def _validate_threshold_identity(snapshot: CommitThresholdSnapshot) -> None:
    for name in ("threshold_id", "issuer_id", "provenance", "trace_event_id"):
        require_commit_text(getattr(snapshot, name), f"commit threshold {name}")
    for name in (
        "risk_policy_root",
        "risk_assessment_fingerprint",
        "risk_chain_id",
        "risk_chain_state_fingerprint",
    ):
        require_commit_fingerprint(getattr(snapshot, name), f"commit threshold {name}")
    if (
        require_commit_step(
            snapshot.risk_chain_revision,
            "commit threshold risk_chain_revision",
        )
        <= 0
    ):
        raise GovernanceError("commit threshold chain revision must be positive")
    if type(snapshot.risk_band) is not RiskBand:
        raise GovernanceError("commit threshold risk band is invalid")
    if type(snapshot.minimum_assurance) is not CommitAssurance:
        raise GovernanceError("commit threshold minimum assurance is invalid")


def _validate_threshold_numeric_bounds(snapshot: CommitThresholdSnapshot) -> None:
    for name in (
        "minimum_positive_evidence",
        "maximum_counterevidence",
        "minimum_support_clusters",
        "minimum_source_diversity",
        "minimum_margin",
        "stability_steps",
    ):
        require_commit_step(getattr(snapshot, name), f"commit threshold {name}")
    if snapshot.minimum_positive_evidence <= 0:
        raise GovernanceError("commit threshold positive evidence must be positive")
    if snapshot.minimum_support_clusters <= 0:
        raise GovernanceError("commit threshold support clusters must be positive")
    if snapshot.minimum_source_diversity <= 0:
        raise GovernanceError("commit threshold diversity must be positive")
    if snapshot.minimum_margin <= 0 or snapshot.stability_steps <= 0:
        raise GovernanceError("commit threshold margin/window must be positive")
    require_scaled_integer(
        snapshot.maximum_counterevidence_ratio_ppm,
        "commit threshold maximum counterevidence ratio",
        maximum=WEIGHT_SCALE,
    )
    ratio = require_scaled_integer(
        snapshot.minimum_support_ratio_ppm,
        "commit threshold minimum support ratio",
        maximum=WEIGHT_SCALE,
    )
    if ratio <= 0:
        raise GovernanceError("commit threshold support ratio must be positive")


def _validate_threshold_labels(snapshot: CommitThresholdSnapshot) -> None:
    require_commit_labels(
        snapshot.required_challenge_categories,
        "commit threshold required challenge categories",
    )
    require_commit_labels(
        snapshot.publishable_outcomes,
        "commit threshold publishable outcomes",
        allow_empty=True,
    )
    require_commit_labels(
        snapshot.executable_outcomes,
        "commit threshold executable outcomes",
        allow_empty=True,
    )


def _validate_threshold_authority_window(snapshot: CommitThresholdSnapshot) -> None:
    if type(snapshot.authority) is not AuthorityLevel or not can_verify(
        snapshot.authority
    ):
        raise GovernanceError("commit threshold authority is invalid")
    issued = require_commit_step(
        snapshot.issued_at_step,
        "commit threshold issued_at_step",
    )
    expires = require_commit_step(
        snapshot.expires_at_step,
        "commit threshold expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("commit threshold expiry must be after issuance")


def _threshold_values(snapshot: CommitThresholdSnapshot) -> tuple[object, ...]:
    return _risk_band_values(
        RiskBandPolicy(
            minimum_positive_evidence=snapshot.minimum_positive_evidence,
            maximum_counterevidence=snapshot.maximum_counterevidence,
            maximum_counterevidence_ratio_ppm=(
                snapshot.maximum_counterevidence_ratio_ppm
            ),
            minimum_support_clusters=snapshot.minimum_support_clusters,
            minimum_support_ratio_ppm=snapshot.minimum_support_ratio_ppm,
            minimum_source_diversity=snapshot.minimum_source_diversity,
            minimum_margin=snapshot.minimum_margin,
            stability_steps=snapshot.stability_steps,
            required_challenge_categories=list(snapshot.required_challenge_categories),
            minimum_assurance=snapshot.minimum_assurance.value,
            publishable_outcomes=list(snapshot.publishable_outcomes),
            executable_outcomes=list(snapshot.executable_outcomes),
        )
    )


def _canonical_fingerprints(
    values: Sequence[str],
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(values)
    if not normalized:
        raise GovernanceError(f"{field_name} must not be empty")
    for value in normalized:
        require_commit_fingerprint(value, field_name)
    if len(normalized) != len(set(normalized)):
        raise GovernanceError(f"{field_name} contains a duplicate")
    return tuple(sorted(normalized))


_PUBLIC_MODULE = "pheroos.governance.risk"
for _public_object in (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    RiskBand,
):
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object
