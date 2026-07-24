"""Portable contracts for one durable, policy-bound Risk v2 lineage.

Portable values prove canonical integrity only.  Store inclusion, finality, and
currentness are established by :mod:`pheroos.governance._risk_v2.operations`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
)
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.protocol.extensions import is_namespaced_extension

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _freeze_json_mapping,
    _portable_json,
    _require_root,
)
from pheroos.governance._risk_policy import RiskBand
from pheroos.governance._risk_v2.resources import (
    MAX_RISK_INPUT_ROOTS_V2,
    MAX_RISK_RATIONALE_CODES_V2,
    MAX_RISK_RESOURCE_DEPTH_V2,
    MAX_RISK_RESOURCE_NODES_V2,
    MAX_RISK_RESOURCE_TEXT_BYTES_V2,
    MAX_RISK_SNAPSHOT_BYTES_V2,
    MAX_RISK_SOURCE_TRACE_ROOTS_V2,
    MAX_RISK_TEXT_BYTES_V2,
    MAX_RISK_THRESHOLD_LABELS_V2,
    _canonical_roots,
    _canonical_texts,
    _require_canonical_wire_v2,
    _install_exact_root,
    _preflight_portable_resources_v2,
    _require_bounded_text,
    _require_count,
    _require_exact_mapping,
    _require_exact_version,
    _root,
)


RISK_ASSESSMENT_RECORD_SCHEMA_V2 = "pheroos-risk-assessment-record-v2"
RISK_THRESHOLD_SNAPSHOT_SCHEMA_V2 = "pheroos-risk-threshold-snapshot-v2"
RISK_STATE_SNAPSHOT_SCHEMA_V2 = "pheroos-risk-state-snapshot-v2"
RISK_STATE_ADVANCE_REQUEST_SCHEMA_V2 = "pheroos-risk-state-advance-request-v2"
RISK_STATE_SCHEMA_V2 = "pheroos-risk-state-v2"

RISK_GENESIS_SNAPSHOT_ROOT_V2 = _root(
    "genesis-parent",
    {
        "schema": RISK_STATE_SNAPSHOT_SCHEMA_V2,
        "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
    },
)
RISK_GENESIS_TRANSITION_ID_V2 = "genesis"


def risk_state_stream_ref_v2(
    scope_ref: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    risk_policy_root: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    """Return the sole Risk v2 stream for an exact target/run/policy binding.

    Epoch is intentionally state carried by this fixed lineage rather than a
    stream-identity component.  This keeps long-lived runs sealable and makes
    an epoch change an auditable state transition instead of a new ledger.
    """

    text_values = tuple(
        _require_bounded_text(value, f"risk stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("profile", profile),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    if type(assurance) is not CommitAssurance:
        raise TypeError("risk stream assurance is invalid")
    for label, value in (
        ("manifest_root", manifest_root),
        ("commit_policy_root", commit_policy_root),
        ("risk_policy_root", risk_policy_root),
    ):
        _require_root(value, f"risk stream {label}")
    material = (
        text_values[0],
        text_values[1],
        assurance.value,
        manifest_root,
        commit_policy_root,
        risk_policy_root,
        text_values[2],
        text_values[3],
        text_values[4],
    )
    digest = sha256("\x00".join(material).encode("utf-8")).hexdigest()
    return f"authority:risk-v2:{digest}"


def risk_state_transition_id_v2(stream_ref: str, advance_ref: str) -> str:
    stream = _require_bounded_text(stream_ref, "risk transition stream_ref")
    advance = _require_bounded_text(advance_ref, "risk transition advance_ref")
    digest = sha256(
        stream.encode("utf-8") + b"\x00" + advance.encode("utf-8")
    ).hexdigest()
    return f"transition:risk-v2:{digest}"


@dataclass(frozen=True, slots=True)
class RiskAssessmentRecordV2:
    """Portable assessment meaning, without a claim of Store authority."""

    assessment_ref: str
    issuer_ref: str
    risk_band: RiskBand
    risk_input_roots: Sequence[str]
    rationale_codes: Sequence[str]
    assessment_method: str
    issued_at_step: int
    expires_at_step: int
    previous_assessment_root: str
    window_reset_required: bool
    provenance_ref: str
    source_trace_roots: Sequence[str]
    schema: str = RISK_ASSESSMENT_RECORD_SCHEMA_V2
    assessment_root: str = ""

    _root_field: ClassVar[str] = "assessment_root"

    def __post_init__(self) -> None:
        _require_exact_version(
            self.schema, RISK_ASSESSMENT_RECORD_SCHEMA_V2, "risk assessment schema"
        )
        for field in (
            "assessment_ref",
            "issuer_ref",
            "assessment_method",
            "provenance_ref",
        ):
            _require_bounded_text(getattr(self, field), f"risk assessment {field}")
        if type(self.risk_band) is not RiskBand:
            raise TypeError("risk assessment band is invalid")
        roots = _canonical_roots(self.risk_input_roots, "risk assessment input roots")
        rationales = _canonical_texts(
            self.rationale_codes,
            "risk assessment rationale codes",
            limit=MAX_RISK_RATIONALE_CODES_V2,
        )
        object.__setattr__(self, "risk_input_roots", roots)
        object.__setattr__(self, "rationale_codes", rationales)
        source_trace_roots = _canonical_roots(
            self.source_trace_roots,
            "risk assessment source trace roots",
            limit=MAX_RISK_SOURCE_TRACE_ROOTS_V2,
        )
        object.__setattr__(self, "source_trace_roots", source_trace_roots)
        issued = _require_count(self.issued_at_step, "risk assessment issued_at_step")
        expires = _require_count(
            self.expires_at_step, "risk assessment expires_at_step"
        )
        if expires <= issued:
            raise ValueError("risk assessment expiry must be after issuance")
        if self.previous_assessment_root:
            _require_root(
                self.previous_assessment_root,
                "risk assessment previous_assessment_root",
            )
        if type(self.window_reset_required) is not bool:
            raise TypeError(
                "risk assessment window_reset_required must be an exact bool"
            )
        if not self.previous_assessment_root and self.window_reset_required:
            raise ValueError("initial risk assessment cannot require a window reset")
        _install_exact_root(
            self, "assessment_root", self.assessment_root, "assessment", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "assessment_ref": self.assessment_ref,
            "issuer_ref": self.issuer_ref,
            "risk_band": self.risk_band.value,
            "risk_input_roots": list(self.risk_input_roots),
            "rationale_codes": list(self.rationale_codes),
            "assessment_method": self.assessment_method,
            "issued_at_step": self.issued_at_step,
            "expires_at_step": self.expires_at_step,
            "previous_assessment_root": self.previous_assessment_root,
            "window_reset_required": self.window_reset_required,
            "provenance_ref": self.provenance_ref,
            "source_trace_roots": list(self.source_trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "assessment_root": self.assessment_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.assessment_root

    @classmethod
    def from_dict(cls, payload: object) -> RiskAssessmentRecordV2:
        value = _require_exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "assessment_ref",
                    "issuer_ref",
                    "risk_band",
                    "risk_input_roots",
                    "rationale_codes",
                    "assessment_method",
                    "issued_at_step",
                    "expires_at_step",
                    "previous_assessment_root",
                    "window_reset_required",
                    "provenance_ref",
                    "source_trace_roots",
                    "assessment_root",
                }
            ),
            "risk assessment record v2",
        )
        try:
            value["risk_band"] = RiskBand(cast(str, value["risk_band"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("risk assessment band is unsupported") from exc
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "risk assessment record v2",
        )
        return decoded


@dataclass(frozen=True, slots=True)
class RiskThresholdSnapshotV2:
    """Complete projection of the selected declared risk-band threshold."""

    assessment_root: str
    risk_policy_root: str
    risk_band: RiskBand
    minimum_positive_evidence: int
    maximum_counterevidence: int
    maximum_counterevidence_ratio_ppm: int
    minimum_support_clusters: int
    minimum_support_ratio_ppm: int
    minimum_source_diversity: int
    minimum_margin: int
    stability_steps: int
    required_challenge_categories: Sequence[str]
    minimum_assurance: CommitAssurance
    publishable_outcomes: Sequence[str]
    executable_outcomes: Sequence[str]
    extensions: Mapping[str, object]
    schema: str = RISK_THRESHOLD_SNAPSHOT_SCHEMA_V2
    threshold_root: str = ""

    _root_field: ClassVar[str] = "threshold_root"

    def __post_init__(self) -> None:
        _require_exact_version(
            self.schema, RISK_THRESHOLD_SNAPSHOT_SCHEMA_V2, "risk threshold schema"
        )
        _require_root(self.assessment_root, "risk threshold assessment_root")
        _require_root(self.risk_policy_root, "risk threshold risk_policy_root")
        if type(self.risk_band) is not RiskBand:
            raise TypeError("risk threshold band is invalid")
        for field in (
            "minimum_positive_evidence",
            "maximum_counterevidence",
            "maximum_counterevidence_ratio_ppm",
            "minimum_support_clusters",
            "minimum_support_ratio_ppm",
            "minimum_source_diversity",
            "minimum_margin",
            "stability_steps",
        ):
            _require_count(getattr(self, field), f"risk threshold {field}")
        if (
            self.minimum_positive_evidence <= 0
            or self.minimum_support_clusters <= 0
            or self.minimum_source_diversity <= 0
            or self.minimum_margin <= 0
            or self.stability_steps <= 0
        ):
            raise ValueError("risk threshold positive minima must be positive")
        if self.maximum_counterevidence_ratio_ppm > 1_000_000:
            raise ValueError("risk threshold counterevidence ratio exceeds one")
        if not 0 < self.minimum_support_ratio_ppm <= 1_000_000:
            raise ValueError("risk threshold support ratio is outside its bound")
        if type(self.minimum_assurance) is not CommitAssurance:
            raise TypeError("risk threshold minimum assurance is invalid")
        for field, allow_empty in (
            ("required_challenge_categories", False),
            ("publishable_outcomes", True),
            ("executable_outcomes", True),
        ):
            object.__setattr__(
                self,
                field,
                _canonical_texts(
                    getattr(self, field),
                    f"risk threshold {field}",
                    limit=MAX_RISK_THRESHOLD_LABELS_V2,
                    allow_empty=allow_empty,
                ),
            )
        _preflight_portable_resources_v2(self.extensions)
        frozen_extensions = _freeze_json_mapping(
            self.extensions, "$.risk_threshold.extensions"
        )
        if any(not is_namespaced_extension(key) for key in frozen_extensions):
            raise ValueError("risk threshold extensions must use namespaced keys")
        object.__setattr__(self, "extensions", frozen_extensions)
        _install_exact_root(
            self, "threshold_root", self.threshold_root, "threshold", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "assessment_root": self.assessment_root,
            "risk_policy_root": self.risk_policy_root,
            "risk_band": self.risk_band.value,
            "minimum_positive_evidence": self.minimum_positive_evidence,
            "maximum_counterevidence": self.maximum_counterevidence,
            "maximum_counterevidence_ratio_ppm": self.maximum_counterevidence_ratio_ppm,
            "minimum_support_clusters": self.minimum_support_clusters,
            "minimum_support_ratio_ppm": self.minimum_support_ratio_ppm,
            "minimum_source_diversity": self.minimum_source_diversity,
            "minimum_margin": self.minimum_margin,
            "stability_steps": self.stability_steps,
            "required_challenge_categories": list(self.required_challenge_categories),
            "minimum_assurance": self.minimum_assurance.value,
            "publishable_outcomes": list(self.publishable_outcomes),
            "executable_outcomes": list(self.executable_outcomes),
            "extensions": _portable_json(self.extensions),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "threshold_root": self.threshold_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.threshold_root

    @classmethod
    def from_dict(cls, payload: object) -> RiskThresholdSnapshotV2:
        value = _require_exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "assessment_root",
                    "risk_policy_root",
                    "risk_band",
                    "minimum_positive_evidence",
                    "maximum_counterevidence",
                    "maximum_counterevidence_ratio_ppm",
                    "minimum_support_clusters",
                    "minimum_support_ratio_ppm",
                    "minimum_source_diversity",
                    "minimum_margin",
                    "stability_steps",
                    "required_challenge_categories",
                    "minimum_assurance",
                    "publishable_outcomes",
                    "executable_outcomes",
                    "extensions",
                    "threshold_root",
                }
            ),
            "risk threshold snapshot v2",
        )
        try:
            value["risk_band"] = RiskBand(cast(str, value["risk_band"]))
            value["minimum_assurance"] = CommitAssurance(
                cast(str, value["minimum_assurance"])
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("risk threshold enum value is unsupported") from exc
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "risk threshold snapshot v2",
        )
        return decoded


@dataclass(frozen=True, slots=True)
class RiskStateSnapshotV2:
    """Complete replacement state for one durable Risk v2 lineage."""

    domain_root: str
    scope_ref: str
    manifest_root: str
    commit_policy_root: str
    risk_policy_root: str
    profile: str
    assurance: CommitAssurance
    protocol_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    stream_ref: str
    transition_id: str
    advance_ref: str
    revision: int
    current_step: int
    parent_revision: int
    parent_epoch: int | None
    parent_transition_id: str
    parent_snapshot_root: str
    assessment: RiskAssessmentRecordV2
    threshold: RiskThresholdSnapshotV2
    source_context_root: str
    schema: str = RISK_STATE_SNAPSHOT_SCHEMA_V2
    state_schema: str = RISK_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        _validate_risk_snapshot_shape(self)
        _validate_risk_snapshot_record_binding(self)
        _validate_risk_snapshot_identity(self)
        _install_exact_root(
            self, "snapshot_root", self.snapshot_root, "snapshot", self._body()
        )
        if len(_canonical_bytes(self.to_dict())) > MAX_RISK_SNAPSHOT_BYTES_V2:
            raise ValueError("risk canonical snapshot exceeds its byte bound")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state_schema": self.state_schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "risk_policy_root": self.risk_policy_root,
            "profile": self.profile,
            "assurance": self.assurance.value,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "epoch": self.epoch,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "advance_ref": self.advance_ref,
            "revision": self.revision,
            "current_step": self.current_step,
            "parent_revision": self.parent_revision,
            "parent_epoch": self.parent_epoch,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "assessment": self.assessment.to_dict(),
            "threshold": self.threshold.to_dict(),
            "source_context_root": self.source_context_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.snapshot_root

    @classmethod
    def from_dict(cls, payload: object) -> RiskStateSnapshotV2:
        value = _require_exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "state_schema",
                    "canonical_version",
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
                    "epoch",
                    "stream_ref",
                    "transition_id",
                    "advance_ref",
                    "revision",
                    "current_step",
                    "parent_revision",
                    "parent_epoch",
                    "parent_transition_id",
                    "parent_snapshot_root",
                    "assessment",
                    "threshold",
                    "source_context_root",
                    "snapshot_root",
                }
            ),
            "risk state snapshot v2",
        )
        try:
            value["assurance"] = CommitAssurance(cast(str, value["assurance"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("risk snapshot assurance is unsupported") from exc
        value["assessment"] = RiskAssessmentRecordV2.from_dict(value["assessment"])
        value["threshold"] = RiskThresholdSnapshotV2.from_dict(value["threshold"])
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "risk state snapshot v2",
        )
        return decoded


def _validate_risk_snapshot_shape(snapshot: RiskStateSnapshotV2) -> None:
    _require_exact_version(
        snapshot.schema, RISK_STATE_SNAPSHOT_SCHEMA_V2, "risk snapshot schema"
    )
    _require_exact_version(
        snapshot.state_schema, RISK_STATE_SCHEMA_V2, "risk state schema"
    )
    _require_exact_version(
        snapshot.canonical_version,
        AUTHORITY_CANONICAL_VERSION_V2,
        "risk snapshot canonical version",
    )
    for field in (
        "domain_root",
        "manifest_root",
        "commit_policy_root",
        "risk_policy_root",
        "parent_snapshot_root",
        "source_context_root",
    ):
        _require_root(getattr(snapshot, field), f"risk snapshot {field}")
    for field in (
        "scope_ref",
        "profile",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
        "transition_id",
        "advance_ref",
        "parent_transition_id",
    ):
        _require_bounded_text(getattr(snapshot, field), f"risk snapshot {field}")
    if type(snapshot.assurance) is not CommitAssurance:
        raise TypeError("risk snapshot assurance is invalid")
    for field in ("epoch", "revision", "current_step", "parent_revision"):
        _require_count(getattr(snapshot, field), f"risk snapshot {field}")
    if snapshot.revision < 1 or snapshot.parent_revision != snapshot.revision - 1:
        raise ValueError("risk snapshot revision continuity is invalid")
    if snapshot.revision == 1:
        _validate_risk_genesis_parent(snapshot)
    elif type(snapshot.parent_epoch) is not int or snapshot.parent_epoch < 0:
        raise ValueError("risk snapshot parent_epoch is invalid")


def _validate_risk_genesis_parent(snapshot: RiskStateSnapshotV2) -> None:
    if snapshot.parent_epoch is not None:
        raise ValueError("risk snapshot genesis parent epoch must be null")
    if snapshot.parent_transition_id != RISK_GENESIS_TRANSITION_ID_V2:
        raise ValueError("risk snapshot genesis parent transition is mismatched")
    if snapshot.parent_snapshot_root != RISK_GENESIS_SNAPSHOT_ROOT_V2:
        raise ValueError("risk snapshot genesis parent root is mismatched")


def _validate_risk_snapshot_record_binding(snapshot: RiskStateSnapshotV2) -> None:
    if type(snapshot.assessment) is not RiskAssessmentRecordV2:
        raise TypeError("risk snapshot assessment is invalid")
    if type(snapshot.threshold) is not RiskThresholdSnapshotV2:
        raise TypeError("risk snapshot threshold is invalid")
    if (
        snapshot.threshold.assessment_root != snapshot.assessment.assessment_root
        or snapshot.threshold.risk_policy_root != snapshot.risk_policy_root
        or snapshot.threshold.risk_band is not snapshot.assessment.risk_band
    ):
        raise ValueError("risk snapshot assessment/threshold binding is mismatched")
    if not (
        snapshot.assessment.issued_at_step
        <= snapshot.current_step
        < snapshot.assessment.expires_at_step
    ):
        raise ValueError("risk snapshot assessment is not fresh at current_step")


def _validate_risk_snapshot_identity(snapshot: RiskStateSnapshotV2) -> None:
    expected_stream = risk_state_stream_ref_v2(
        snapshot.scope_ref,
        snapshot.profile,
        snapshot.assurance,
        snapshot.manifest_root,
        snapshot.commit_policy_root,
        snapshot.risk_policy_root,
        snapshot.protocol_ref,
        snapshot.run_ref,
        snapshot.target_ref,
    )
    expected_transition = risk_state_transition_id_v2(
        expected_stream, snapshot.advance_ref
    )
    if (
        snapshot.stream_ref != expected_stream
        or snapshot.transition_id != expected_transition
    ):
        raise ValueError("risk snapshot stream or transition identity is mismatched")


@dataclass(frozen=True, slots=True)
class RiskStateAdvanceRequestV2:
    """Idempotent request binding one exact next Risk v2 snapshot."""

    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    advance_ref: str
    transition_id: str
    stream_ref: str
    snapshot: RiskStateSnapshotV2
    schema: str = RISK_STATE_ADVANCE_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    _root_field: ClassVar[str] = "request_root"

    def __post_init__(self) -> None:
        _require_exact_version(
            self.schema,
            RISK_STATE_ADVANCE_REQUEST_SCHEMA_V2,
            "risk state advance request schema",
        )
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "risk state advance request canonical version",
        )
        if type(self.snapshot) is not RiskStateSnapshotV2:
            raise TypeError("risk state request requires exact snapshot v2")
        _require_root(self.domain_root, "risk state request domain_root")
        for field in (
            "scope_ref",
            "run_ref",
            "target_ref",
            "advance_ref",
            "transition_id",
            "stream_ref",
        ):
            _require_bounded_text(
                getattr(self, field),
                f"risk state request {field}",
            )
        _require_count(self.epoch, "risk state request epoch")
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "epoch",
            "advance_ref",
            "transition_id",
            "stream_ref",
        ):
            if getattr(self, field) != getattr(self.snapshot, field):
                raise ValueError(
                    f"risk state request {field} is cross-bound incorrectly"
                )
        _install_exact_root(
            self, "request_root", self.request_root, "advance-request", self._body()
        )

    @property
    def observed_epoch(self) -> int:
        return self.epoch

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "epoch": self.epoch,
            "advance_ref": self.advance_ref,
            "transition_id": self.transition_id,
            "stream_ref": self.stream_ref,
            "snapshot": self.snapshot.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.request_root

    @classmethod
    def from_dict(cls, payload: object) -> RiskStateAdvanceRequestV2:
        value = _require_exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "domain_root",
                    "scope_ref",
                    "run_ref",
                    "target_ref",
                    "epoch",
                    "advance_ref",
                    "transition_id",
                    "stream_ref",
                    "snapshot",
                    "request_root",
                }
            ),
            "risk state advance request v2",
        )
        value["snapshot"] = RiskStateSnapshotV2.from_dict(value["snapshot"])
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "risk state advance request v2",
        )
        return decoded


__all__ = [
    "MAX_RISK_INPUT_ROOTS_V2",
    "MAX_RISK_RATIONALE_CODES_V2",
    "MAX_RISK_SOURCE_TRACE_ROOTS_V2",
    "MAX_RISK_RESOURCE_DEPTH_V2",
    "MAX_RISK_RESOURCE_NODES_V2",
    "MAX_RISK_RESOURCE_TEXT_BYTES_V2",
    "MAX_RISK_SNAPSHOT_BYTES_V2",
    "MAX_RISK_TEXT_BYTES_V2",
    "RISK_ASSESSMENT_RECORD_SCHEMA_V2",
    "RISK_GENESIS_SNAPSHOT_ROOT_V2",
    "RISK_GENESIS_TRANSITION_ID_V2",
    "RISK_STATE_ADVANCE_REQUEST_SCHEMA_V2",
    "RISK_STATE_SCHEMA_V2",
    "RISK_STATE_SNAPSHOT_SCHEMA_V2",
    "RISK_THRESHOLD_SNAPSHOT_SCHEMA_V2",
    "RiskAssessmentRecordV2",
    "RiskStateAdvanceRequestV2",
    "RiskStateSnapshotV2",
    "RiskThresholdSnapshotV2",
    "risk_state_stream_ref_v2",
    "risk_state_transition_id_v2",
]
