"""Portable request/result records for scoped baseline-output v2.

The request contains proposal data and an exact Protocol-owned manifest.  It
does not contain a caller decision, a publication boolean, or a portable
credential.  ``ActionPermissionV2`` is portable committed data; possession of
the dataclass is not authority without matching StateStore inclusion and
currentness.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from pheroos.protocol.authority_manifest_v2 import (
    BaselineOutputActionPolicyV2,
    ScopedProtocolManifestV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
)

from pheroos.governance._authority_session_v2.contracts import (
    _canonical_bytes,
    _compute_root,
    _exact_object,
    _install_derived_text,
    _install_root,
    _require_epoch,
    _require_exact_version,
    _require_root,
    _require_text,
    _require_transition_id,
    _stream_ref,
)
from pheroos.governance._authority_store_v2_contracts.foundation import (
    _freeze_json_mapping,
    _portable_json,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)


BASELINE_OUTPUT_REQUEST_SCHEMA_V2 = "pheroos-governance-baseline-output-request-v2"
ACTION_PERMISSION_SCHEMA_V2 = "pheroos-governance-action-permission-v2"
BASELINE_OUTPUT_RESULT_SCHEMA_V2 = "pheroos-governance-baseline-output-result-v2"
BASELINE_MANIFEST_STATE_SCHEMA_V2 = "pheroos-governance-baseline-manifest-state-v2"
BASELINE_EVIDENCE_STATE_SCHEMA_V2 = "pheroos-governance-baseline-evidence-state-v2"
BASELINE_STOP_STATE_SCHEMA_V2 = "pheroos-governance-baseline-stop-state-v2"
BASELINE_DECISION_STATE_SCHEMA_V2 = "pheroos-governance-baseline-decision-state-v2"
BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2 = (
    "pheroos-governance-baseline-action-permission-state-v2"
)
BASELINE_OUTPUT_STATE_SCHEMA_V2 = "pheroos-governance-baseline-output-state-v2"

_SUPPORTED_EFFECTS = frozenset({"publish", "execute"})
_TERMINAL_STATUSES = frozenset(
    {"evidence_commit", "safe_fallback", "blocked", "invalid", "finality_unavailable"}
)
_ACTIONABLE_TERMINAL_STATUSES = frozenset({"evidence_commit", "safe_fallback"})
_SIGNAL_FIELDS = {
    "candidate_ref",
    "evidence_root",
    "provenance_ref",
    "signal_ref",
    "signal_root",
    "signal_transition_id",
    "source_ref",
}
_STOP_FIELDS = {"action_ref", "blocked", "provenance_ref", "reason_ref"}


class ActionPermissionDispositionV2(StrEnum):
    AUTHORIZED = "authorized"
    DENIED = "denied"


class BaselineOutputTerminalStatusV2(StrEnum):
    EVIDENCE_COMMIT = "evidence_commit"
    SAFE_FALLBACK = "safe_fallback"
    BLOCKED = "blocked"
    INVALID = "invalid"
    FINALITY_UNAVAILABLE = "finality_unavailable"


class BaselineOutputDeliveryDispositionV2(StrEnum):
    DELIVERABLE = "deliverable"
    RETRY_REQUIRED = "retry_required"


class BaselineOutputActionDispositionV2(StrEnum):
    AUTHORIZED = "authorized"
    DENIED = "denied"


def baseline_manifest_stream_ref_v2(scope_ref: str, protocol_ref: str) -> str:
    _require_text(scope_ref, "baseline manifest scope_ref")
    _require_text(protocol_ref, "baseline manifest protocol_ref")
    return _stream_ref("baseline-manifest", (scope_ref, protocol_ref))


def baseline_evidence_stream_ref_v2(
    scope_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    return _bound_stream("baseline-evidence", scope_ref, run_ref, target_ref)


def baseline_stop_stream_ref_v2(
    scope_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    return _bound_stream("baseline-stop", scope_ref, run_ref, target_ref)


def baseline_decision_stream_ref_v2(
    scope_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    return _bound_stream("baseline-decision", scope_ref, run_ref, target_ref)


def baseline_action_permission_stream_ref_v2(
    scope_ref: str,
    run_ref: str,
    target_ref: str,
    action_ref: str,
) -> str:
    return _bound_stream(
        "baseline-action-permission",
        scope_ref,
        run_ref,
        target_ref,
        action_ref,
    )


def baseline_output_stream_ref_v2(
    scope_ref: str,
    run_ref: str,
    target_ref: str,
    action_ref: str,
) -> str:
    return _bound_stream(
        "baseline-output",
        scope_ref,
        run_ref,
        target_ref,
        action_ref,
    )


def baseline_verified_signal_proposal_root_v2(
    *,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
    target_ref: str,
    candidate_ref: str,
    signal_ref: str,
    evidence_root: str,
    provenance_ref: str,
    source_ref: str,
) -> str:
    """Bind every quorum-relevant proposal field to a verified signal root."""

    _require_root(domain_root, "baseline verified signal domain_root")
    for label, value in (
        ("scope_ref", scope_ref),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
        ("candidate_ref", candidate_ref),
        ("signal_ref", signal_ref),
        ("source_ref", source_ref),
    ):
        _require_text(value, f"baseline verified signal {label}")
    _require_root(evidence_root, "baseline verified signal evidence_root")
    _require_root(provenance_ref, "baseline verified signal provenance_ref")
    return _compute_root(
        "baseline-verified-signal-proposal",
        {
            "domain_root": domain_root,
            "scope_ref": scope_ref,
            "run_ref": run_ref,
            "target_ref": target_ref,
            "candidate_ref": candidate_ref,
            "signal_ref": signal_ref,
            "evidence_root": evidence_root,
            "provenance_ref": provenance_ref,
            "source_ref": source_ref,
        },
    )


@dataclass(frozen=True, slots=True)
class BaselineOutputRequestV2:
    """One exact aggregate request; every embedded signal/stop value is a proposal."""

    domain_root: str
    scope_ref: str
    run_ref: str
    request_ref: str
    output_transition_id: str
    manifest: ScopedProtocolManifestV2
    target_ref: str
    action_ref: str
    proposed_candidate_ref: str | None
    verified_signals: tuple[Mapping[str, Any], ...]
    stop_resolutions: tuple[Mapping[str, Any], ...]
    output_payload: Mapping[str, Any]
    observed_epoch: int
    manifest_stream_ref: str = ""
    evidence_stream_ref: str = ""
    stop_stream_ref: str = ""
    decision_stream_ref: str = ""
    permission_stream_ref: str = ""
    output_stream_ref: str = ""
    output_payload_root: str = ""
    schema: str = BASELINE_OUTPUT_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    def __post_init__(self) -> None:
        _validate_request_identity(self)
        _validate_request_manifest(self)
        signals = _freeze_signals(self.verified_signals, self)
        stops = _freeze_stops(self.stop_resolutions, self.manifest, self.target_ref)
        payload = _freeze_json_mapping(self.output_payload, "$.output_payload")
        object.__setattr__(self, "verified_signals", signals)
        object.__setattr__(self, "stop_resolutions", stops)
        object.__setattr__(self, "output_payload", payload)
        _install_request_streams(self)
        payload_root = _compute_root(
            "baseline-output-payload",
            _portable_json(payload),
        )
        _install_exact_root(
            self,
            "output_payload_root",
            self.output_payload_root,
            payload_root,
        )
        _require_exact_version(
            self.schema,
            BASELINE_OUTPUT_REQUEST_SCHEMA_V2,
            "baseline output request schema",
        )
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "baseline output request canonical_version",
        )
        _install_root(
            self,
            "request_root",
            self.request_root,
            "baseline-output-request",
            self._body(),
        )

    @property
    def effect(self) -> str:
        return _request_action(self).effect

    @property
    def output_policy_root(self) -> str:
        return self.manifest.output_policy.policy_root

    @property
    def permission_transition_id(self) -> str:
        return _stage_transition_id(self.output_transition_id, "permission")

    def stage_transition_id(self, role: str) -> str:
        if role not in {"manifest", "evidence", "stop", "decision", "permission"}:
            raise ValueError("baseline output stage role is unsupported")
        return _stage_transition_id(self.output_transition_id, role)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "request_ref": self.request_ref,
            "output_transition_id": self.output_transition_id,
            "manifest": self.manifest.to_dict(),
            "target_ref": self.target_ref,
            "action_ref": self.action_ref,
            "proposed_candidate_ref": self.proposed_candidate_ref,
            "verified_signals": [
                _portable_json(item) for item in self.verified_signals
            ],
            "stop_resolutions": [
                _portable_json(item) for item in self.stop_resolutions
            ],
            "output_payload": _portable_json(self.output_payload),
            "observed_epoch": self.observed_epoch,
            "manifest_stream_ref": self.manifest_stream_ref,
            "evidence_stream_ref": self.evidence_stream_ref,
            "stop_stream_ref": self.stop_stream_ref,
            "decision_stream_ref": self.decision_stream_ref,
            "permission_stream_ref": self.permission_stream_ref,
            "output_stream_ref": self.output_stream_ref,
            "output_payload_root": self.output_payload_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.request_root

    @classmethod
    def from_dict(cls, payload: object) -> BaselineOutputRequestV2:
        fields = set(_REQUEST_FIELDS)
        value = _exact_object(payload, fields, "baseline output request")
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            run_ref=value["run_ref"],
            request_ref=value["request_ref"],
            output_transition_id=value["output_transition_id"],
            manifest=ScopedProtocolManifestV2.from_dict(value["manifest"]),
            target_ref=value["target_ref"],
            action_ref=value["action_ref"],
            proposed_candidate_ref=value["proposed_candidate_ref"],
            verified_signals=_mapping_tuple_from_wire(
                value["verified_signals"],
                "verified_signals",
            ),
            stop_resolutions=_mapping_tuple_from_wire(
                value["stop_resolutions"],
                "stop_resolutions",
            ),
            output_payload=value["output_payload"],
            observed_epoch=value["observed_epoch"],
            manifest_stream_ref=value["manifest_stream_ref"],
            evidence_stream_ref=value["evidence_stream_ref"],
            stop_stream_ref=value["stop_stream_ref"],
            decision_stream_ref=value["decision_stream_ref"],
            permission_stream_ref=value["permission_stream_ref"],
            output_stream_ref=value["output_stream_ref"],
            output_payload_root=value["output_payload_root"],
            schema=value["schema"],
            canonical_version=value["canonical_version"],
            request_root=value["request_root"],
        )


@dataclass(frozen=True, slots=True)
class ActionPermissionV2:
    """Portable permission record; only matching current inclusion is authority."""

    domain_root: str
    scope_ref: str
    run_ref: str
    request_ref: str
    request_root: str
    permission_transition_id: str
    permission_stream_ref: str
    manifest_root: str
    output_policy_root: str
    evidence_root: str
    stop_root: str
    decision_root: str
    target_ref: str
    candidate_ref: str
    action_ref: str
    effect: str
    terminal_status: BaselineOutputTerminalStatusV2
    output_payload_root: str
    disposition: ActionPermissionDispositionV2
    issued_epoch: int
    expires_at_epoch: int
    grant_ref: str
    grant_root: str
    grant_binding_ref: str
    schema: str = ACTION_PERMISSION_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    permission_root: str = ""

    def __post_init__(self) -> None:
        _validate_permission(self)
        _install_root(
            self,
            "permission_root",
            self.permission_root,
            "baseline-action-permission",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "request_ref": self.request_ref,
            "request_root": self.request_root,
            "permission_transition_id": self.permission_transition_id,
            "permission_stream_ref": self.permission_stream_ref,
            "manifest_root": self.manifest_root,
            "output_policy_root": self.output_policy_root,
            "evidence_root": self.evidence_root,
            "stop_root": self.stop_root,
            "decision_root": self.decision_root,
            "target_ref": self.target_ref,
            "candidate_ref": self.candidate_ref,
            "action_ref": self.action_ref,
            "effect": self.effect,
            "terminal_status": self.terminal_status.value,
            "output_payload_root": self.output_payload_root,
            "disposition": self.disposition.value,
            "issued_epoch": self.issued_epoch,
            "expires_at_epoch": self.expires_at_epoch,
            "grant_ref": self.grant_ref,
            "grant_root": self.grant_root,
            "grant_binding_ref": self.grant_binding_ref,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "permission_root": self.permission_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.permission_root

    @classmethod
    def from_dict(cls, payload: object) -> ActionPermissionV2:
        value = _exact_object(
            payload,
            set(_PERMISSION_FIELDS),
            "baseline action permission",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            run_ref=value["run_ref"],
            request_ref=value["request_ref"],
            request_root=value["request_root"],
            permission_transition_id=value["permission_transition_id"],
            permission_stream_ref=value["permission_stream_ref"],
            manifest_root=value["manifest_root"],
            output_policy_root=value["output_policy_root"],
            evidence_root=value["evidence_root"],
            stop_root=value["stop_root"],
            decision_root=value["decision_root"],
            target_ref=value["target_ref"],
            candidate_ref=value["candidate_ref"],
            action_ref=value["action_ref"],
            effect=value["effect"],
            terminal_status=BaselineOutputTerminalStatusV2(value["terminal_status"]),
            output_payload_root=value["output_payload_root"],
            disposition=ActionPermissionDispositionV2(value["disposition"]),
            issued_epoch=value["issued_epoch"],
            expires_at_epoch=value["expires_at_epoch"],
            grant_ref=value["grant_ref"],
            grant_root=value["grant_root"],
            grant_binding_ref=value["grant_binding_ref"],
            schema=value["schema"],
            canonical_version=value["canonical_version"],
            permission_root=value["permission_root"],
        )


@dataclass(frozen=True, slots=True)
class BaselineOutputResultV2:
    """Total output result; delivery and current external action stay separate."""

    domain_root: str
    scope_ref: str
    run_ref: str
    request_ref: str
    request_root: str
    output_transition_id: str
    output_payload_root: str
    terminal_status: BaselineOutputTerminalStatusV2 | None
    candidate_ref: str | None
    delivery_disposition: BaselineOutputDeliveryDispositionV2
    action_disposition: BaselineOutputActionDispositionV2
    permission_root: str
    authorization: ActionPermissionV2 | None
    commit_attempt: GovernanceCommitAttemptV2
    result_root: str
    schema: str = BASELINE_OUTPUT_RESULT_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2

    def __post_init__(self) -> None:
        _validate_result(self)

    @property
    def disposition(self) -> GovernanceCommitDispositionV2:
        return self.commit_attempt.disposition

    @property
    def position(self) -> GovernanceCommitPositionV2 | None:
        observation = self.commit_attempt.position_observation
        return None if observation is None else observation.position

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "request_ref": self.request_ref,
            "request_root": self.request_root,
            "output_transition_id": self.output_transition_id,
            "output_payload_root": self.output_payload_root,
            "terminal_status": (
                None if self.terminal_status is None else self.terminal_status.value
            ),
            "candidate_ref": self.candidate_ref,
            "delivery_disposition": self.delivery_disposition.value,
            "action_disposition": self.action_disposition.value,
            "permission_root": self.permission_root,
            "authorization": (
                None if self.authorization is None else self.authorization.to_dict()
            ),
            "commit_attempt": self.commit_attempt.to_dict(),
            "result_root": self.result_root,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.result_root

    @classmethod
    def from_dict(cls, payload: object) -> BaselineOutputResultV2:
        value = _exact_object(payload, set(_RESULT_FIELDS), "baseline output result")
        terminal = value["terminal_status"]
        authorization = value["authorization"]
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            run_ref=value["run_ref"],
            request_ref=value["request_ref"],
            request_root=value["request_root"],
            output_transition_id=value["output_transition_id"],
            output_payload_root=value["output_payload_root"],
            terminal_status=(
                None if terminal is None else BaselineOutputTerminalStatusV2(terminal)
            ),
            candidate_ref=value["candidate_ref"],
            delivery_disposition=BaselineOutputDeliveryDispositionV2(
                value["delivery_disposition"]
            ),
            action_disposition=BaselineOutputActionDispositionV2(
                value["action_disposition"]
            ),
            permission_root=value["permission_root"],
            authorization=(
                None
                if authorization is None
                else ActionPermissionV2.from_dict(authorization)
            ),
            commit_attempt=GovernanceCommitAttemptV2.from_dict(value["commit_attempt"]),
            result_root=value["result_root"],
            schema=value["schema"],
            canonical_version=value["canonical_version"],
        )


def baseline_output_result_root_v2(
    request: BaselineOutputRequestV2,
    *,
    terminal_status: BaselineOutputTerminalStatusV2,
    candidate_ref: str,
    permission_root: str,
) -> str:
    if type(request) is not BaselineOutputRequestV2:
        raise TypeError("baseline result root requires an exact request")
    if type(terminal_status) is not BaselineOutputTerminalStatusV2:
        raise TypeError("baseline result root terminal_status is invalid")
    _require_text(candidate_ref, "baseline result candidate_ref")
    _require_root(permission_root, "baseline result permission_root")
    return _compute_root(
        "baseline-output-result",
        {
            "schema": BASELINE_OUTPUT_RESULT_SCHEMA_V2,
            "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
            "domain_root": request.domain_root,
            "scope_ref": request.scope_ref,
            "run_ref": request.run_ref,
            "request_ref": request.request_ref,
            "request_root": request.request_root,
            "output_transition_id": request.output_transition_id,
            "output_payload_root": request.output_payload_root,
            "terminal_status": terminal_status.value,
            "candidate_ref": candidate_ref,
            "delivery_disposition": BaselineOutputDeliveryDispositionV2.DELIVERABLE.value,
            "permission_root": permission_root,
        },
    )


def _validate_request_identity(request: BaselineOutputRequestV2) -> None:
    _require_root(request.domain_root, "baseline output request domain_root")
    for field_name in (
        "scope_ref",
        "run_ref",
        "request_ref",
        "target_ref",
        "action_ref",
    ):
        _require_text(
            getattr(request, field_name),
            f"baseline output request {field_name}",
        )
    _require_transition_id(
        request.output_transition_id,
        "baseline output request output_transition_id",
    )
    _require_epoch(request.observed_epoch, "baseline output request observed_epoch")
    if request.observed_epoch == MAX_AUTHORITY_REVISION_V2:
        raise ValueError(
            "baseline output request observed_epoch leaves no permission expiry epoch"
        )
    if request.proposed_candidate_ref is not None:
        _require_text(
            request.proposed_candidate_ref,
            "baseline output request proposed_candidate_ref",
        )


def _validate_request_manifest(request: BaselineOutputRequestV2) -> None:
    if type(request.manifest) is not ScopedProtocolManifestV2:
        raise TypeError("baseline output request requires an exact scoped manifest")
    target_ids = {item.id for item in request.manifest.targets}
    if request.target_ref not in target_ids:
        raise ValueError("baseline output request target is not declared")
    candidate_ids = {
        item.id
        for item in request.manifest.candidates
        if item.target == request.target_ref
    }
    if not candidate_ids:
        raise ValueError("baseline output request target has no declared candidates")
    action = _request_action(request)
    if action.target != request.target_ref:
        raise ValueError("baseline output request action target is mismatched")
    decision_mode = request.manifest.output_policy.decision_mode
    if decision_mode == "direct_governance":
        if request.proposed_candidate_ref not in candidate_ids:
            raise ValueError("direct governance candidate is not declared")
    elif decision_mode == "quorum":
        if request.proposed_candidate_ref is not None:
            raise ValueError("quorum request cannot carry a direct candidate")
    else:
        raise ValueError("baseline output decision mode is unsupported")


def _request_action(request: BaselineOutputRequestV2) -> BaselineOutputActionPolicyV2:
    actions = [
        item
        for item in request.manifest.output_policy.actions
        if item.action_ref == request.action_ref
    ]
    if len(actions) != 1:
        raise ValueError("baseline output request action is not declared exactly once")
    return actions[0]


def _freeze_signals(
    value: object,
    request: BaselineOutputRequestV2,
) -> tuple[Mapping[str, Any], ...]:
    if type(value) is not tuple:
        raise TypeError("baseline verified_signals must be an exact tuple")
    frozen = tuple(_freeze_signal(item, index) for index, item in enumerate((value)))
    keys = tuple(
        (item["source_ref"].encode("utf-8"), item["signal_ref"].encode("utf-8"))
        for item in frozen
    )
    if len(keys) != len(set(keys)) or keys != tuple(sorted(keys)):
        raise ValueError("baseline verified_signals must be unique and UTF-8 sorted")
    for index, item in enumerate(frozen):
        expected_root = baseline_verified_signal_proposal_root_v2(
            domain_root=request.domain_root,
            scope_ref=request.scope_ref,
            run_ref=request.run_ref,
            target_ref=request.target_ref,
            candidate_ref=cast(str, item["candidate_ref"]),
            signal_ref=cast(str, item["signal_ref"]),
            evidence_root=cast(str, item["evidence_root"]),
            provenance_ref=cast(str, item["provenance_ref"]),
            source_ref=cast(str, item["source_ref"]),
        )
        if item["signal_root"] != expected_root:
            raise ValueError(
                f"verified_signals/{index}/signal_root does not bind its proposal"
            )
    return frozen


def _freeze_signal(value: object, index: int) -> Mapping[str, Any]:
    item = _exact_mapping(value, _SIGNAL_FIELDS, f"verified_signals/{index}")
    for field_name in (
        "candidate_ref",
        "signal_ref",
        "signal_transition_id",
        "source_ref",
    ):
        _require_text(item[field_name], f"verified_signals/{index}/{field_name}")
    _require_transition_id(
        item["signal_transition_id"],
        f"verified_signals/{index}/signal_transition_id",
    )
    for field_name in ("evidence_root", "provenance_ref", "signal_root"):
        _require_root(item[field_name], f"verified_signals/{index}/{field_name}")
    return _freeze_json_mapping(item, f"$.verified_signals[{index}]")


def _freeze_stops(
    value: object,
    manifest: ScopedProtocolManifestV2,
    target_ref: str,
) -> tuple[Mapping[str, Any], ...]:
    if type(value) is not tuple:
        raise TypeError("baseline stop_resolutions must be an exact tuple")
    frozen = tuple(_freeze_stop(item, index) for index, item in enumerate((value)))
    action_refs = tuple(item["action_ref"] for item in frozen)
    expected = tuple(
        item.action_ref
        for item in manifest.output_policy.actions
        if item.target == target_ref
    )
    if action_refs != expected:
        raise ValueError(
            "baseline stop_resolutions must cover every declared target action"
        )
    return frozen


def _freeze_stop(value: object, index: int) -> Mapping[str, Any]:
    item = _exact_mapping(value, _STOP_FIELDS, f"stop_resolutions/{index}")
    for field_name in ("action_ref", "reason_ref"):
        _require_text(item[field_name], f"stop_resolutions/{index}/{field_name}")
    _require_root(item["provenance_ref"], f"stop_resolutions/{index}/provenance_ref")
    if type(item["blocked"]) is not bool:
        raise TypeError(f"stop_resolutions/{index}/blocked must be an exact bool")
    return _freeze_json_mapping(item, f"$.stop_resolutions[{index}]")


def _install_request_streams(request: BaselineOutputRequestV2) -> None:
    expected = {
        "manifest_stream_ref": baseline_manifest_stream_ref_v2(
            request.scope_ref,
            request.manifest.id,
        ),
        "evidence_stream_ref": baseline_evidence_stream_ref_v2(
            request.scope_ref,
            request.run_ref,
            request.target_ref,
        ),
        "stop_stream_ref": baseline_stop_stream_ref_v2(
            request.scope_ref,
            request.run_ref,
            request.target_ref,
        ),
        "decision_stream_ref": baseline_decision_stream_ref_v2(
            request.scope_ref,
            request.run_ref,
            request.target_ref,
        ),
        "permission_stream_ref": baseline_action_permission_stream_ref_v2(
            request.scope_ref,
            request.run_ref,
            request.target_ref,
            request.action_ref,
        ),
        "output_stream_ref": baseline_output_stream_ref_v2(
            request.scope_ref,
            request.run_ref,
            request.target_ref,
            request.action_ref,
        ),
    }
    for attribute, computed in expected.items():
        _install_derived_text(
            request,
            attribute,
            getattr(request, attribute),
            computed,
            f"baseline output request {attribute}",
        )


def _validate_permission(permission: ActionPermissionV2) -> None:
    for field_name in (
        "domain_root",
        "request_root",
        "manifest_root",
        "output_policy_root",
        "evidence_root",
        "stop_root",
        "decision_root",
        "output_payload_root",
        "grant_root",
        "grant_binding_ref",
    ):
        _require_root(
            getattr(permission, field_name), f"action permission {field_name}"
        )
    for field_name in (
        "scope_ref",
        "run_ref",
        "request_ref",
        "permission_stream_ref",
        "target_ref",
        "candidate_ref",
        "action_ref",
        "grant_ref",
    ):
        _require_text(
            getattr(permission, field_name), f"action permission {field_name}"
        )
    _require_transition_id(
        permission.permission_transition_id,
        "action permission permission_transition_id",
    )
    if permission.effect not in _SUPPORTED_EFFECTS:
        raise ValueError("action permission effect is unsupported")
    if type(permission.terminal_status) is not BaselineOutputTerminalStatusV2:
        raise TypeError("action permission terminal_status is invalid")
    if permission.terminal_status.value not in _TERMINAL_STATUSES:
        raise ValueError("action permission terminal_status is unsupported")
    if type(permission.disposition) is not ActionPermissionDispositionV2:
        raise TypeError("action permission disposition is invalid")
    if (
        permission.disposition is ActionPermissionDispositionV2.AUTHORIZED
        and permission.terminal_status.value not in _ACTIONABLE_TERMINAL_STATUSES
    ):
        raise ValueError("non-actionable terminal status cannot be authorized")
    issued = _require_epoch(permission.issued_epoch, "action permission issued_epoch")
    expires = _require_epoch(
        permission.expires_at_epoch,
        "action permission expires_at_epoch",
    )
    if expires <= issued:
        raise ValueError("action permission expiry must follow issuance")
    _require_exact_version(
        permission.schema,
        ACTION_PERMISSION_SCHEMA_V2,
        "action permission schema",
    )
    _require_exact_version(
        permission.canonical_version,
        AUTHORITY_CANONICAL_VERSION_V2,
        "action permission canonical_version",
    )


def _validate_result(result: BaselineOutputResultV2) -> None:
    _validate_result_identity(result)
    _validate_result_authorization(result)
    _validate_result_reachability(result)
    _require_exact_version(
        result.schema,
        BASELINE_OUTPUT_RESULT_SCHEMA_V2,
        "baseline output result schema",
    )
    _require_exact_version(
        result.canonical_version,
        AUTHORITY_CANONICAL_VERSION_V2,
        "baseline output result canonical_version",
    )


def _validate_result_identity(result: BaselineOutputResultV2) -> None:
    for field_name in (
        "domain_root",
        "request_root",
        "output_payload_root",
        "permission_root",
        "result_root",
    ):
        _require_root(getattr(result, field_name), f"baseline result {field_name}")
    for field_name in ("scope_ref", "run_ref", "request_ref"):
        _require_text(getattr(result, field_name), f"baseline result {field_name}")
    _require_transition_id(
        result.output_transition_id,
        "baseline result output_transition_id",
    )
    if type(result.commit_attempt) is not GovernanceCommitAttemptV2:
        raise TypeError("baseline result requires an exact commit attempt")
    _validate_result_attempt_binding(result)
    if type(result.delivery_disposition) is not BaselineOutputDeliveryDispositionV2:
        raise TypeError("baseline result delivery disposition is invalid")
    if type(result.action_disposition) is not BaselineOutputActionDispositionV2:
        raise TypeError("baseline result action disposition is invalid")


def _validate_result_authorization(result: BaselineOutputResultV2) -> None:
    if (
        result.authorization is not None
        and type(result.authorization) is not ActionPermissionV2
    ):
        raise TypeError("baseline result authorization is invalid")
    if result.authorization is not None and (
        result.action_disposition is not BaselineOutputActionDispositionV2.AUTHORIZED
    ):
        raise ValueError("denied baseline result cannot expose authorization")
    if result.authorization is not None:
        _validate_result_permission_binding(result, result.authorization)
    if result.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED and (
        result.authorization is None
        or result.commit_attempt.disposition
        is not GovernanceCommitDispositionV2.COMMITTED
        or result.position is not GovernanceCommitPositionV2.CURRENT
    ):
        raise ValueError("baseline action authorization requires a current commit")


def _validate_result_permission_binding(
    result: BaselineOutputResultV2,
    permission: ActionPermissionV2,
) -> None:
    _require_permission_matches_result(result, permission)
    if permission.disposition is not ActionPermissionDispositionV2.AUTHORIZED:
        raise ValueError("baseline result authorization must be authorized")
    expected_stream = baseline_output_stream_ref_v2(
        result.scope_ref,
        result.run_ref,
        permission.target_ref,
        permission.action_ref,
    )
    if result.commit_attempt.stream_ref != expected_stream:
        raise ValueError("baseline result commit attempt binding is mismatched")


def _require_permission_matches_result(
    result: BaselineOutputResultV2,
    permission: ActionPermissionV2,
) -> None:
    expected = (
        result.domain_root,
        result.scope_ref,
        result.run_ref,
        result.request_ref,
        result.request_root,
        f"{result.output_transition_id}:permission",
        result.output_payload_root,
        result.terminal_status,
        result.candidate_ref,
        result.permission_root,
    )
    observed = (
        permission.domain_root,
        permission.scope_ref,
        permission.run_ref,
        permission.request_ref,
        permission.request_root,
        permission.permission_transition_id,
        permission.output_payload_root,
        permission.terminal_status,
        permission.candidate_ref,
        permission.permission_root,
    )
    if observed != expected:
        raise ValueError("baseline result authorization binding is mismatched")


def _validate_result_attempt_binding(result: BaselineOutputResultV2) -> None:
    attempt = result.commit_attempt
    if (
        attempt.domain_root != result.domain_root
        or attempt.scope_ref != result.scope_ref
        or attempt.transition_id != result.output_transition_id
    ):
        raise ValueError("baseline result commit attempt binding is mismatched")
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        return
    transition = attempt.committed_transition
    if transition is None or transition.batch.transition is None:
        raise ValueError("committed baseline result is missing output state")
    state = transition.batch.transition.state_records
    if not isinstance(state, Mapping):
        raise TypeError("committed baseline output state must be a mapping")
    try:
        permission = ActionPermissionV2.from_dict(_portable_json(state["permission"]))
        expected = (
            BASELINE_OUTPUT_STATE_SCHEMA_V2,
            result.domain_root,
            result.scope_ref,
            result.request_root,
            result.output_payload_root,
            result.permission_root,
            result.result_root,
            result.candidate_ref,
            None if result.terminal_status is None else result.terminal_status.value,
            BaselineOutputDeliveryDispositionV2.DELIVERABLE.value,
        )
        observed = (
            state["schema"],
            state["domain_root"],
            state["scope_ref"],
            state["request_root"],
            state["output_payload_root"],
            state["permission_root"],
            state["result_root"],
            state["candidate_ref"],
            state["terminal_status"],
            state["delivery_disposition"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("committed baseline output state is invalid") from exc
    _require_permission_matches_result(result, permission)
    expected_stream = baseline_output_stream_ref_v2(
        result.scope_ref,
        result.run_ref,
        permission.target_ref,
        permission.action_ref,
    )
    if observed != expected or attempt.stream_ref != expected_stream:
        raise ValueError("committed baseline output state binding is mismatched")


def _validate_result_reachability(result: BaselineOutputResultV2) -> None:
    if (
        result.delivery_disposition
        is BaselineOutputDeliveryDispositionV2.RETRY_REQUIRED
    ):
        if (
            result.commit_attempt.disposition
            is not GovernanceCommitDispositionV2.RETRY_REQUIRED
            or result.terminal_status is not None
            or result.candidate_ref is not None
        ):
            raise ValueError("retry result must remain non-terminal")
    else:
        if type(result.terminal_status) is not BaselineOutputTerminalStatusV2:
            raise TypeError("deliverable baseline result requires terminal status")
        if result.candidate_ref is None:
            raise ValueError("deliverable baseline result requires candidate_ref")
        _require_text(result.candidate_ref, "baseline result candidate_ref")
    expected_root = _baseline_result_root_from_fields(result)
    if result.result_root != expected_root:
        raise ValueError("baseline output result_root is mismatched")


def _baseline_result_root_from_fields(result: BaselineOutputResultV2) -> str:
    if (
        result.delivery_disposition
        is BaselineOutputDeliveryDispositionV2.RETRY_REQUIRED
    ):
        return _compute_root(
            "baseline-output-retry",
            {
                "request_root": result.request_root,
                "attempt_root": result.commit_attempt.attempt_root,
            },
        )
    assert result.terminal_status is not None
    assert result.candidate_ref is not None
    return _compute_root(
        "baseline-output-result",
        {
            "schema": result.schema,
            "canonical_version": result.canonical_version,
            "domain_root": result.domain_root,
            "scope_ref": result.scope_ref,
            "run_ref": result.run_ref,
            "request_ref": result.request_ref,
            "request_root": result.request_root,
            "output_transition_id": result.output_transition_id,
            "output_payload_root": result.output_payload_root,
            "terminal_status": result.terminal_status.value,
            "candidate_ref": result.candidate_ref,
            "delivery_disposition": result.delivery_disposition.value,
            "permission_root": result.permission_root,
        },
    )


def _bound_stream(kind: str, *bindings: str) -> str:
    for index, value in enumerate(bindings):
        _require_text(value, f"{kind} binding/{index}")
    return _stream_ref(kind, tuple(bindings))


def _stage_transition_id(output_transition_id: str, role: str) -> str:
    _require_transition_id(output_transition_id, "baseline output_transition_id")
    _require_text(role, "baseline stage role")
    return f"{output_transition_id}:{role}"


def _install_exact_root(
    instance: object,
    attribute: str,
    supplied: object,
    computed: str,
) -> None:
    if type(supplied) is str and supplied == "":
        object.__setattr__(instance, attribute, computed)
        return
    _require_root(supplied, attribute)
    if supplied != computed:
        raise ValueError(f"{attribute} is mismatched")


def _exact_mapping(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    projected = {key: item for key, item in value.items()}
    if set(projected) != fields:
        raise ValueError(f"{label} fields are invalid")
    return projected


def _mapping_tuple_from_wire(
    value: object, label: str
) -> tuple[Mapping[str, Any], ...]:
    if type(value) is not list:
        raise TypeError(f"baseline output {label} wire value must be an array")
    if any(type(item) is not dict for item in value):
        raise TypeError(f"baseline output {label} entries must be exact objects")
    return tuple(cast(list[dict[str, Any]], value))


_REQUEST_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "run_ref",
        "request_ref",
        "output_transition_id",
        "manifest",
        "target_ref",
        "action_ref",
        "proposed_candidate_ref",
        "verified_signals",
        "stop_resolutions",
        "output_payload",
        "observed_epoch",
        "manifest_stream_ref",
        "evidence_stream_ref",
        "stop_stream_ref",
        "decision_stream_ref",
        "permission_stream_ref",
        "output_stream_ref",
        "output_payload_root",
        "request_root",
    }
)

_PERMISSION_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "run_ref",
        "request_ref",
        "request_root",
        "permission_transition_id",
        "permission_stream_ref",
        "manifest_root",
        "output_policy_root",
        "evidence_root",
        "stop_root",
        "decision_root",
        "target_ref",
        "candidate_ref",
        "action_ref",
        "effect",
        "terminal_status",
        "output_payload_root",
        "disposition",
        "issued_epoch",
        "expires_at_epoch",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "permission_root",
    }
)

_RESULT_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "run_ref",
        "request_ref",
        "request_root",
        "output_transition_id",
        "output_payload_root",
        "terminal_status",
        "candidate_ref",
        "delivery_disposition",
        "action_disposition",
        "permission_root",
        "authorization",
        "commit_attempt",
        "result_root",
    }
)


__all__ = [
    "ACTION_PERMISSION_SCHEMA_V2",
    "BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2",
    "BASELINE_DECISION_STATE_SCHEMA_V2",
    "BASELINE_EVIDENCE_STATE_SCHEMA_V2",
    "BASELINE_MANIFEST_STATE_SCHEMA_V2",
    "BASELINE_OUTPUT_REQUEST_SCHEMA_V2",
    "BASELINE_OUTPUT_RESULT_SCHEMA_V2",
    "BASELINE_OUTPUT_STATE_SCHEMA_V2",
    "BASELINE_STOP_STATE_SCHEMA_V2",
    "ActionPermissionDispositionV2",
    "ActionPermissionV2",
    "BaselineOutputActionDispositionV2",
    "BaselineOutputDeliveryDispositionV2",
    "BaselineOutputRequestV2",
    "BaselineOutputResultV2",
    "BaselineOutputTerminalStatusV2",
    "baseline_action_permission_stream_ref_v2",
    "baseline_decision_stream_ref_v2",
    "baseline_evidence_stream_ref_v2",
    "baseline_manifest_stream_ref_v2",
    "baseline_output_result_root_v2",
    "baseline_output_stream_ref_v2",
    "baseline_stop_stream_ref_v2",
    "baseline_verified_signal_proposal_root_v2",
]
