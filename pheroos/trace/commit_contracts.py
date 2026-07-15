from __future__ import annotations

"""Event-specific Trace ABI contracts for Optimal Commit.

The module deliberately depends only on the Protocol wire codec and the
standard library.  It validates portable JSON lineage and reconstructs a
commit decision chain without importing governance implementation objects.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any
import re
import unicodedata

COMMIT_TRACE_PAYLOAD_VERSION = "pheroos-commit-trace-payload-v1"
COMMIT_TRACE_EVENT_SCHEMA = "pheroos-commit-trace-event-v1"
COMMIT_WIRE_VERSION = "pheroos-commit-wire-v1"
MAX_AUTHORITY_INTEGER = (2**53) - 1
SUPPORTED_COMMIT_PROFILES = frozenset(
    {
        "pheroos-commit-integrity-v1",
        "pheroos-hybrid-commit-v1",
        "pheroos-certified-commit-v1",
        "pheroos-distributed-commit-v1",
    }
)

_ROOT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_NONCRITICAL_EXTENSION_RE = re.compile(r"^(?:x-.+|ext\..+)$")
_CRITICAL_EXTENSION_PREFIXES = ("x-critical", "ext.critical")

_TEXT = "text"
_STRING = "string"
_ROOT = "root"
_INTEGER = "integer"
_STEP = "step"
_COUNT = "count"
_BOOL = "bool"
_TEXTS = "texts"
_ROOTS = "roots"
_PAYLOAD = "payload"


def _trace_wire_fingerprint(
    payload: Mapping[str, Any],
    *,
    schema: str,
    profile: str,
    version: str = COMMIT_WIRE_VERSION,
) -> str:
    """Independently reproduce the Commit wire root inside Trace ABI.

    Trace cannot import Protocol by package-boundary contract.  Keeping this
    tiny independent verifier is intentional: cross-surface conformance tests
    prove it byte-for-byte equivalent to the Protocol-owned encoder.
    """

    bindings: dict[str, str] = {}
    for name, value in (
        ("schema", schema),
        ("profile", profile),
        ("version", version),
    ):
        _require_text(value, f"commit trace canonical {name}")
        bindings[name] = value
    normalized = _trace_wire_value(payload, path="payload")
    if not isinstance(normalized, dict):  # pragma: no cover - Mapping above
        raise ValueError("commit trace canonical payload must be an object")
    canonical = json.dumps(
        {
            "payload": normalized,
            "profile": bindings["profile"],
            "schema": bindings["schema"],
            "version": bindings["version"],
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _trace_wire_value(value: Any, *, path: str) -> Any:
    if isinstance(value, Enum):
        return _trace_wire_value(value.value, path=path)
    if value is None or type(value) is bool:
        return value
    if isinstance(value, str):
        if value != unicodedata.normalize("NFC", value):
            raise ValueError(f"{path} must already use NFC normalization")
        return value
    if type(value) is int:
        if abs(value) > MAX_AUTHORITY_INTEGER:
            raise ValueError(f"{path} exceeds the authority integer bound")
        return value
    if isinstance(value, float):
        raise ValueError(f"{path} must not contain floating-point values")
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            _require_text(key, f"{path} key")
            if key in normalized:
                raise ValueError(f"{path} contains duplicate keys")
            normalized[key] = _trace_wire_value(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [
            _trace_wire_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ValueError(f"{path} contains an unsupported wire value")


@dataclass(frozen=True)
class CommitTraceEventContract:
    required: Mapping[str, object]
    optional: Mapping[str, object] = MappingProxyType({})
    predecessor_groups: tuple[frozenset[str], ...] = ()


def _contract(
    required: Mapping[str, object],
    *,
    optional: Mapping[str, object] | None = None,
    predecessors: tuple[frozenset[str], ...] = (),
) -> CommitTraceEventContract:
    return CommitTraceEventContract(
        required=MappingProxyType(dict(required)),
        optional=MappingProxyType(dict(optional or {})),
        predecessor_groups=predecessors,
    )


_ATTESTED = frozenset({"principal_attested"})
_VERIFIED_PRINCIPAL = frozenset({"principal_verified"})
_VERIFIED_OBSERVATION = frozenset({"observation_verified"})
_EVIDENCE_BOUND = frozenset({"evidence_bound"})
_MEMBERSHIP = frozenset({"membership_snapshot"})
_LEASE = frozenset({"support_lease_issued"})
_RISK = frozenset({"risk_assessed"})
_STOP = frozenset({"stop_resolution_verified"})
_PERMISSION = frozenset({"action_permission_issued"})
_METRICS = frozenset({"commit_metrics"})
_WINDOW = frozenset({"commit_window_advanced", "commit_window_reset"})
_CERT_OR_PROVISIONAL = frozenset(
    {"commit_certificate_issued", "commit_provisional"}
)
_WITNESS = frozenset({"quorum_witness"})
_OUTCOME = frozenset({"decision_outcome"})


COMMIT_EVENT_CONTRACTS: Mapping[str, CommitTraceEventContract] = MappingProxyType(
    {
        "principal_attested": _contract(
            {
                "principal_id": _TEXT,
                "attestation_fingerprint": _ROOT,
                "nonce": _TEXT,
            }
        ),
        "principal_verified": _contract(
            {
                "principal_id": _TEXT,
                "cluster_id": _TEXT,
                "attestation_ref": _ROOT,
                "verification_ref": _ROOT,
            },
            predecessors=(_ATTESTED,),
        ),
        "risk_assessed": _contract(
            {
                "risk_band": frozenset({"LOW", "MODERATE", "HIGH", "CRITICAL"}),
                "risk_ref": _ROOT,
                "threshold_ref": _ROOT,
                "risk_chain_revision": _COUNT,
            }
        ),
        "membership_snapshot": _contract(
            {
                "snapshot_id": _TEXT,
                "membership_root": _ROOT,
                "snapshot_ref": _ROOT,
                "cluster_count": _COUNT,
                "expires_at_step": _STEP,
            },
            predecessors=(_VERIFIED_PRINCIPAL,),
        ),
        "observation_recorded": _contract(
            {
                "observation_id": _TEXT,
                "candidate_id": _TEXT,
                "polarity": frozenset({"support", "contradict"}),
                "principal_id": _TEXT,
                "nonce": _TEXT,
                "attestation_fingerprint": _ROOT,
            },
            predecessors=(_ATTESTED,),
        ),
        "observation_verified": _contract(
            {
                "observation_id": _TEXT,
                "candidate_id": _TEXT,
                "polarity": frozenset({"support", "contradict"}),
                "principal_cluster_id": _TEXT,
                "observation_ref": _ROOT,
                "principal_verification_ref": _ROOT,
            },
            predecessors=(frozenset({"observation_recorded"}), _VERIFIED_PRINCIPAL),
        ),
        "counterevidence_disposed": _contract(
            {
                "disposition_id": _TEXT,
                "disposition_ref": _ROOT,
                "candidate_id": _TEXT,
                "counter_observation_ref": _ROOT,
                "disposition": frozenset(
                    {"unresolved", "rebutted", "accepted", "immaterial"}
                ),
                "rebuttal_refs": _ROOTS,
                "resolution_ref": _STRING,
            },
            predecessors=(_VERIFIED_OBSERVATION,),
        ),
        "challenge_recorded": _contract(
            {
                "challenge_id": _TEXT,
                "candidate_id": _TEXT,
                "category": _TEXT,
                "result": frozenset(
                    {"no_counterevidence", "counterevidence_found", "inconclusive"}
                ),
                "challenge_ref": _ROOT,
                "principal_verification_ref": _ROOT,
            },
            predecessors=(_VERIFIED_PRINCIPAL,),
        ),
        "evidence_bound": _contract(
            {
                "candidate_id": _TEXT,
                "claim_fingerprint": _ROOT,
                "binding_ref": _ROOT,
                "positive_root": _ROOT,
                "counter_root": _ROOT,
                "disposition_root": _ROOT,
                "challenge_root": _ROOT,
                "evidence_root": _ROOT,
            },
            predecessors=(_VERIFIED_OBSERVATION,),
        ),
        "support_lease_issued": _contract(
            {
                "lease_id": _TEXT,
                "candidate_id": _TEXT,
                "principal_cluster_id": _TEXT,
                "lease_ref": _ROOT,
                "evidence_refs": _ROOTS,
                "expires_at_step": _STEP,
            },
            predecessors=(_EVIDENCE_BOUND, _VERIFIED_PRINCIPAL, _MEMBERSHIP),
        ),
        "support_lease_revoked": _contract(
            {
                "revocation_id": _TEXT,
                "candidate_id": _TEXT,
                "principal_cluster_id": _TEXT,
                "lease_ref": _ROOT,
                "revocation_ref": _ROOT,
                "reason_codes": _TEXTS,
            },
            predecessors=(_LEASE,),
        ),
        "support_lease_expired": _contract(
            {
                "lease_ref": _ROOT,
                "expiration_ref": _ROOT,
                "expired_at_step": _STEP,
            },
            predecessors=(_LEASE,),
        ),
        "support_equivocation": _contract(
            {
                "finding_id": _TEXT,
                "principal_cluster_id": _TEXT,
                "conflicting_candidates": _TEXTS,
                "conflicting_lease_refs": _ROOTS,
                "finding_ref": _ROOT,
            },
            predecessors=(_LEASE,),
        ),
        "commit_metrics": _contract(
            {
                "assessment_ref": _ROOT,
                "candidate_id": _TEXT,
                "metrics_ref": _ROOT,
                "net_evidence": _INTEGER,
                "support_clusters": _COUNT,
                "source_diversity": _COUNT,
                "margin": _INTEGER,
                "ready_for_stability": _BOOL,
            },
            predecessors=(_EVIDENCE_BOUND, _LEASE, _RISK, _MEMBERSHIP, _STOP, _PERMISSION),
        ),
        "commit_window_advanced": _contract(
            {
                "window_ref": _ROOT,
                "assessment_ref": _ROOT,
                "leader_candidate_id": _STRING,
                "stability_count": _COUNT,
                "required_stability_steps": _COUNT,
                "window_root": _ROOT,
                "reset_count": _COUNT,
            },
            optional={"sealed_window_ref": _ROOT},
            predecessors=(_METRICS,),
        ),
        "commit_window_reset": _contract(
            {
                "window_ref": _ROOT,
                "assessment_ref": _ROOT,
                "prior_window_ref": _ROOT,
                "reset_count": _COUNT,
                "remaining_reset_budget": _COUNT,
                "reason_codes": _TEXTS,
            },
            predecessors=(_METRICS, _WINDOW),
        ),
        "quorum_pending": _contract(
            {
                "progress_ref": _ROOT,
                "assessment_ref": _ROOT,
                "phase": frozenset(
                    {"search", "deliberate", "quorum_pending", "provisional"}
                ),
                "unmet_gates": _TEXTS,
                "absolute_deadline_step": _STEP,
            },
            optional={"sealed_window_ref": _ROOT, "previous_progress_ref": _ROOT},
            predecessors=(_WINDOW,),
        ),
        "decision_outcome": _contract(
            {
                "outcome_ref": _ROOT,
                "kind": frozenset(
                    {
                        "evidence_commit",
                        "safe_fallback",
                        "advisory",
                        "blocked",
                        "invalid",
                        "finality_unavailable",
                        "safety_violation",
                    }
                ),
                "authoritative_commit": _BOOL,
                "epistemically_committed": _BOOL,
                "candidate_id": _STRING,
                "reason_codes": _TEXTS,
            },
            optional={
                "assessment_ref": _ROOT,
                "certificate_ref": _ROOT,
                "sealed_window_ref": _ROOT,
            },
        ),
        "stop_resolution_verified": _contract(
            {
                "action": frozenset(
                    {"commit", "publish", "execute", "epoch_transition", "recovery"}
                ),
                "resolution_ref": _ROOT,
                "blocked": _BOOL,
                "expires_at_step": _STEP,
            }
        ),
        "action_permission_issued": _contract(
            {
                "action": frozenset(
                    {"commit", "publish", "execute", "epoch_transition", "recovery"}
                ),
                "permission_ref": _ROOT,
                "allowed": _BOOL,
                "expires_at_step": _STEP,
            }
        ),
        "commit_certificate_issued": _contract(
            {
                "certificate_kind": frozenset(
                    {"local_receipt", "evidence_commit", "distributed_commit", "outcome"}
                ),
                "certificate_ref": _ROOT,
                "candidate_id": _STRING,
                "claim_fingerprint": _STRING,
                "output_fingerprint": _ROOT,
                "final": _BOOL,
            },
            optional={
                "commit_value_root": _ROOT,
                "issuer_attestation_ref": _TEXT,
            },
            predecessors=(_WINDOW,),
        ),
        "quorum_witness": _contract(
            {
                "witness_ref": _ROOT,
                "commit_value_root": _ROOT,
                "proposal_digest": _ROOT,
                "principal_cluster_id": _TEXT,
                "failure_domain": _TEXT,
                "verified": _BOOL,
                "expires_at_step": _STEP,
            },
            predecessors=(frozenset({"commit_certificate_issued"}),),
        ),
        "epoch_certificate": _contract(
            {
                "certificate_ref": _ROOT,
                "prior_epoch": _COUNT,
                "new_epoch": _COUNT,
                "new_membership_root": _ROOT,
                "recovery_ref": _TEXT,
            },
            predecessors=(_MEMBERSHIP,),
        ),
        "commit_provisional": _contract(
            {
                "state_ref": _ROOT,
                "portable_certificate_ref": _ROOT,
                "candidate_id": _TEXT,
                "witness_count": _COUNT,
                "witness_quorum": _COUNT,
                "final": _BOOL,
            },
            optional={
                "commit_value_root": _ROOT,
                "proposal_digest": _ROOT,
            },
            predecessors=(
                frozenset({"quorum_witness", "commit_certificate_issued"}),
            ),
        ),
        "certificate_conflict": _contract(
            {
                "finding_id": _TEXT,
                "finding_ref": _ROOT,
                "commit_value_roots": _ROOTS,
                "left_certificate_ref": _ROOT,
                "right_certificate_ref": _ROOT,
                "distributed_state_ref": _ROOT,
                "frozen": _BOOL,
            },
            predecessors=(frozenset({"commit_certificate_issued"}),),
        ),
        "output_decided": _contract(
            {
                "authorization_ref": _ROOT,
                "outcome_ref": _ROOT,
                "deliver": _BOOL,
                "publish": _BOOL,
                "execute": _BOOL,
                "reason_codes": _TEXTS,
            },
            optional={
                "certificate_ref": _ROOT,
                "distributed_state_ref": _ROOT,
            },
            predecessors=(_OUTCOME,),
        ),
    }
)

COMMIT_EVENT_TYPES = frozenset(COMMIT_EVENT_CONTRACTS)

_SELF_REFERENCE_FIELDS: Mapping[str, str] = MappingProxyType(
    {
        "principal_attested": "attestation_fingerprint",
        "principal_verified": "verification_ref",
        "risk_assessed": "risk_ref",
        "membership_snapshot": "snapshot_ref",
        "observation_recorded": "attestation_fingerprint",
        "observation_verified": "observation_ref",
        "counterevidence_disposed": "disposition_ref",
        "challenge_recorded": "challenge_ref",
        "evidence_bound": "binding_ref",
        "support_lease_issued": "lease_ref",
        "support_lease_revoked": "revocation_ref",
        "support_lease_expired": "expiration_ref",
        "support_equivocation": "finding_ref",
        "commit_metrics": "metrics_ref",
        "commit_window_advanced": "window_ref",
        "commit_window_reset": "window_ref",
        "quorum_pending": "progress_ref",
        "decision_outcome": "outcome_ref",
        "stop_resolution_verified": "resolution_ref",
        "action_permission_issued": "permission_ref",
        "commit_certificate_issued": "certificate_ref",
        "quorum_witness": "witness_ref",
        "epoch_certificate": "certificate_ref",
        "commit_provisional": "state_ref",
        "certificate_conflict": "finding_ref",
        "output_decided": "authorization_ref",
    }
)

_COMMON_REQUIRED: Mapping[str, object] = MappingProxyType(
    {
        "payload_version": frozenset({COMMIT_TRACE_PAYLOAD_VERSION}),
        "event_id": _ROOT,
        "run_id": _TEXT,
        "profile": frozenset(SUPPORTED_COMMIT_PROFILES),
        "assurance": frozenset(
            {"advisory", "evidence_bound", "certified", "distributed"}
        ),
        "step": _STEP,
        "epoch": _COUNT,
        "manifest_root": _ROOT,
        "commit_policy_root": _ROOT,
        "record_schema": _TEXT,
        "record_payload": _PAYLOAD,
        "record_ref": _ROOT,
        "previous_event_ids": _ROOTS,
    }
)


@dataclass(frozen=True)
class CommitTraceReplay:
    protocol_id: str
    run_id: str
    target: str
    profile: str
    assurance: str
    epoch: int
    event_ids: tuple[str, ...]
    event_types: tuple[str, ...]
    record_refs: tuple[str, ...]
    last_step: int
    outcome_ref: str
    outcome_kind: str
    certificate_refs: tuple[str, ...]
    output_ref: str
    complete: bool


def commit_trace_required_fields(event_type: str) -> frozenset[str]:
    contract = COMMIT_EVENT_CONTRACTS.get(event_type)
    if contract is None:
        return frozenset()
    return frozenset((*_COMMON_REQUIRED.keys(), *contract.required.keys()))


def commit_trace_event_id(
    *,
    event_type: str,
    protocol_id: str,
    target: str,
    reason: str,
    lineage: Mapping[str, Any],
) -> str:
    profile = lineage.get("profile")
    _require_text(profile, "commit trace profile")
    body = {
        "event_type": event_type,
        "lineage": {
            key: value
            for key, value in lineage.items()
            if key not in {"event_id", "extensions"}
        },
        "protocol_id": protocol_id,
        "target": target,
    }
    try:
        return _trace_wire_fingerprint(
            body,
            schema=COMMIT_TRACE_EVENT_SCHEMA,
            profile=str(profile),
        )
    except ValueError as exc:
        raise ValueError(f"invalid commit trace wire payload: {exc}") from exc


def build_commit_trace_lineage(
    *,
    event_type: str,
    protocol_id: str,
    target: str,
    reason: str,
    profile: str,
    assurance: str,
    manifest_root: str,
    commit_policy_root: str,
    run_id: str,
    epoch: int,
    step: int,
    record_schema: str,
    record_payload: Mapping[str, Any],
    previous_event_ids: Iterable[str] = (),
    details: Mapping[str, Any],
    extensions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if event_type not in COMMIT_EVENT_CONTRACTS:
        raise ValueError(f"unsupported commit trace event type: {event_type}")
    if not isinstance(record_payload, Mapping):
        raise ValueError("commit trace record_payload must be an object")
    payload = _portable_value(record_payload, path="record_payload")
    if not isinstance(payload, dict):  # pragma: no cover - Mapping above
        raise ValueError("commit trace record_payload must be an object")
    try:
        record_ref = _trace_wire_fingerprint(
            payload,
            schema=record_schema,
            profile=profile,
        )
    except ValueError as exc:
        raise ValueError(f"invalid commit trace record payload: {exc}") from exc
    normalized_details = _portable_value(details, path="details")
    if not isinstance(normalized_details, dict):  # pragma: no cover - Mapping above
        raise ValueError("commit trace details must be an object")
    self_ref_field = _SELF_REFERENCE_FIELDS[event_type]
    supplied_self_ref = normalized_details.get(self_ref_field)
    if supplied_self_ref not in (None, "", record_ref):
        raise ValueError(
            f"{event_type} trace {self_ref_field} must match its record fingerprint"
        )
    normalized_details[self_ref_field] = record_ref
    lineage: dict[str, Any] = {
        "payload_version": COMMIT_TRACE_PAYLOAD_VERSION,
        "run_id": run_id,
        "profile": profile,
        "assurance": _enum_value(assurance),
        "step": step,
        "epoch": epoch,
        "manifest_root": manifest_root,
        "commit_policy_root": commit_policy_root,
        "record_schema": record_schema,
        "record_payload": payload,
        "record_ref": record_ref,
        "previous_event_ids": sorted(tuple(previous_event_ids)),
        **normalized_details,
    }
    if extensions is not None:
        lineage["extensions"] = _portable_value(extensions, path="extensions")
    lineage["event_id"] = commit_trace_event_id(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        reason=reason,
        lineage=lineage,
    )
    validate_commit_trace_event(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        reason=reason,
        lineage=lineage,
    )
    return lineage


def validate_commit_trace_event(
    *,
    event_type: str,
    protocol_id: str,
    target: str,
    reason: str,
    lineage: Mapping[str, Any],
) -> None:
    contract = COMMIT_EVENT_CONTRACTS.get(event_type)
    if contract is None:
        raise ValueError(f"unsupported commit trace event type: {event_type}")
    if not isinstance(lineage, dict):
        raise ValueError(f"{event_type} trace lineage must be a JSON object")
    allowed = set(_COMMON_REQUIRED) | set(contract.required) | set(contract.optional) | {
        "extensions"
    }
    missing = sorted(
        (set(_COMMON_REQUIRED) | set(contract.required)) - set(lineage)
    )
    if missing:
        raise ValueError(
            f"{event_type} trace lineage missing required fields: {', '.join(missing)}"
        )
    unknown = sorted(set(lineage) - allowed)
    if unknown:
        raise ValueError(
            f"{event_type} trace lineage contains unknown fields: {', '.join(unknown)}"
        )
    for name, spec in _COMMON_REQUIRED.items():
        _validate_field(event_type, name, lineage[name], spec)
    for name, spec in contract.required.items():
        _validate_field(event_type, name, lineage[name], spec)
    for name, spec in contract.optional.items():
        if name in lineage:
            _validate_field(event_type, name, lineage[name], spec)
    _validate_extensions(lineage.get("extensions"), event_type=event_type)

    if not isinstance(protocol_id, str) or not protocol_id.strip():
        raise ValueError("commit trace protocol_id is required")
    if not isinstance(target, str) or not target.strip():
        raise ValueError("commit trace target is required")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("commit trace reason is required")

    previous = lineage["previous_event_ids"]
    if previous != sorted(previous) or len(previous) != len(set(previous)):
        raise ValueError(
            f"{event_type} trace previous_event_ids must be sorted and unique"
        )
    field_specs = {**contract.required, **contract.optional}
    for name, spec in field_specs.items():
        if name in lineage and lineage[name] != _canonical_sequence(
            lineage[name],
            spec=spec,
        ):
            raise ValueError(f"{event_type} trace {name} must use canonical ordering")

    payload = lineage["record_payload"]
    try:
        expected_record_ref = _trace_wire_fingerprint(
            payload,
            schema=lineage["record_schema"],
            profile=lineage["profile"],
        )
    except ValueError as exc:
        raise ValueError(f"{event_type} trace record payload is invalid: {exc}") from exc
    if lineage["record_ref"] != expected_record_ref:
        raise ValueError(f"{event_type} trace record_ref does not bind record_payload")
    self_ref_field = _SELF_REFERENCE_FIELDS[event_type]
    if lineage[self_ref_field] != lineage["record_ref"]:
        raise ValueError(
            f"{event_type} trace {self_ref_field} does not bind record_payload"
        )

    bindings = {
        "protocol_id": protocol_id,
        "target": target,
        "run_id": lineage["run_id"],
        "profile": lineage["profile"],
        "assurance": lineage["assurance"],
        "epoch": lineage["epoch"],
        "manifest_root": lineage["manifest_root"],
        "commit_policy_root": lineage["commit_policy_root"],
    }
    for name, expected in bindings.items():
        if name in payload and _enum_value(payload[name]) != _enum_value(expected):
            raise ValueError(
                f"{event_type} trace record_payload {name} does not match its envelope"
            )
    for name in (*contract.required.keys(), *contract.optional.keys()):
        if name in payload and name in lineage:
            spec = contract.required.get(name, contract.optional.get(name))
            if _normalize_field_compare(payload[name], spec=spec) != (
                _normalize_field_compare(lineage[name], spec=spec)
            ):
                raise ValueError(
                    f"{event_type} trace {name} does not match record_payload"
                )

    expected_event_id = commit_trace_event_id(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        reason=reason,
        lineage=lineage,
    )
    if lineage["event_id"] != expected_event_id:
        raise ValueError(f"{event_type} trace event_id does not bind its full event")
    _validate_event_semantics(event_type, lineage)


def replay_commit_trace(
    events: Iterable[Any],
    *,
    require_complete: bool = True,
) -> CommitTraceReplay:
    accepted: list[Any] = []
    by_id: dict[str, Any] = {}
    by_type: dict[str, list[Any]] = {}
    identity: tuple[str, str, str, str, str, int] | None = None
    last_step = -1
    for raw in events:
        event_type = getattr(raw, "event_type", None)
        if event_type not in COMMIT_EVENT_TYPES:
            continue
        validate = getattr(raw, "validate", None)
        if not callable(validate):
            raise ValueError("commit trace replay requires canonical TraceEvent records")
        validate()
        lineage = raw.lineage
        event_id = lineage["event_id"]
        prior = by_id.get(event_id)
        if prior is not None:
            if prior != raw:
                raise ValueError("commit trace event id replay changed its payload")
            continue
        current_identity = (
            raw.protocol_id,
            lineage["run_id"],
            raw.target,
            lineage["profile"],
            lineage["assurance"],
            lineage["epoch"],
        )
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise ValueError("commit trace replay mixes protocol/run/target/profile/epoch")
        step = lineage["step"]
        if step < last_step:
            raise ValueError("commit trace logical steps must be nondecreasing")
        last_step = step
        missing = sorted(set(lineage["previous_event_ids"]) - set(by_id))
        if missing:
            raise ValueError(
                f"{event_type} trace references unseen predecessor events: {', '.join(missing)}"
            )
        predecessor_types = {
            by_id[item].event_type for item in lineage["previous_event_ids"]
        }
        contract = COMMIT_EVENT_CONTRACTS[event_type]
        for group in contract.predecessor_groups:
            if not predecessor_types.intersection(group):
                raise ValueError(
                    f"{event_type} trace lacks required predecessor type from "
                    + ", ".join(sorted(group))
                )
        if event_type == "commit_provisional":
            witness_count = lineage["witness_count"]
            required_predecessor = (
                "commit_certificate_issued"
                if witness_count == 0
                else "quorum_witness"
            )
            if required_predecessor not in predecessor_types:
                raise ValueError(
                    "zero-witness provisional trace requires the portable "
                    "certificate predecessor"
                    if witness_count == 0
                    else "witness-bearing provisional trace requires a quorum "
                    "witness predecessor"
                )
            proposal_present = "proposal_digest" in lineage
            value_present = "commit_value_root" in lineage
            if (
                witness_count == 0
                and (proposal_present or value_present)
            ) or (
                witness_count > 0
                and (not proposal_present or not value_present)
            ):
                raise ValueError(
                    "zero-witness provisional trace cannot claim a proposal/value"
                    if witness_count == 0
                    else "witness-bearing provisional trace requires the exact "
                    "proposal digest and commit value root"
                )
            if witness_count > 0 and not any(
                item.lineage["proposal_digest"] == lineage["proposal_digest"]
                and item.lineage["commit_value_root"]
                == lineage["commit_value_root"]
                and item.lineage["event_id"] in lineage["previous_event_ids"]
                for item in by_type.get("quorum_witness", [])
            ):
                raise ValueError(
                    "witness-bearing provisional trace lacks its exact proposal/value witness"
                )
            portable_ref = lineage["portable_certificate_ref"]
            portable_events = tuple(
                item
                for item in by_type.get("commit_certificate_issued", [])
                if item.lineage["certificate_kind"] == "evidence_commit"
                and item.lineage["certificate_ref"] == portable_ref
            )
            if not portable_events:
                raise ValueError(
                    "provisional trace lacks its exact portable certificate lineage"
                )
            if witness_count == 0 and not any(
                item.lineage["event_id"] in lineage["previous_event_ids"]
                for item in portable_events
            ):
                raise ValueError(
                    "zero-witness provisional trace must directly depend on its "
                    "portable certificate"
                )
        elif event_type == "certificate_conflict":
            conflict_refs = {
                lineage["left_certificate_ref"],
                lineage["right_certificate_ref"],
            }
            certificate_events = tuple(
                item
                for item in by_type.get("commit_certificate_issued", [])
                if item.lineage["certificate_kind"] == "distributed_commit"
                and item.lineage["event_id"] in lineage["previous_event_ids"]
            )
            if not conflict_refs.issubset(
                {item.lineage["certificate_ref"] for item in certificate_events}
            ):
                raise ValueError(
                    "certificate conflict trace lacks both distributed certificate lineages"
                )
            if {
                item.lineage["commit_value_root"] for item in certificate_events
            } != set(lineage["commit_value_roots"]):
                raise ValueError(
                    "certificate conflict trace commit values do not match its certificates"
                )
        by_id[event_id] = raw
        by_type.setdefault(event_type, []).append(raw)
        accepted.append(raw)

    if not accepted or identity is None:
        raise ValueError("commit trace replay requires at least one commit event")
    outcomes = by_type.get("decision_outcome", [])
    outputs = by_type.get("output_decided", [])
    if len(outcomes) > 1:
        raise ValueError("commit trace contains multiple terminal outcomes")
    if len(outputs) > 1:
        raise ValueError("commit trace contains multiple terminal outputs")
    complete = len(outcomes) == 1 and len(outputs) == 1
    if require_complete and not complete:
        raise ValueError("commit trace is not terminally complete")
    outcome_ref = outcomes[0].lineage["outcome_ref"] if outcomes else ""
    outcome_kind = outcomes[0].lineage["kind"] if outcomes else ""
    output_ref = outputs[0].lineage["authorization_ref"] if outputs else ""
    if outputs:
        output = outputs[0].lineage
        if output["outcome_ref"] != outcome_ref:
            raise ValueError("commit output does not reference the terminal outcome")
        if accepted[-1].lineage["event_id"] != outputs[0].lineage["event_id"]:
            raise ValueError("commit output must be the final commit trace event")
        _validate_terminal_output(outcome_kind, outcomes[0].lineage, output)
    certificate_refs = tuple(
        item.lineage["certificate_ref"]
        for item in by_type.get("commit_certificate_issued", [])
    )
    _validate_terminal_path(outcome_kind, by_type, outcomes)
    protocol_id, run_id, target, profile, assurance, epoch = identity
    return CommitTraceReplay(
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        profile=profile,
        assurance=assurance,
        epoch=epoch,
        event_ids=tuple(item.lineage["event_id"] for item in accepted),
        event_types=tuple(item.event_type for item in accepted),
        record_refs=tuple(item.lineage["record_ref"] for item in accepted),
        last_step=last_step,
        outcome_ref=outcome_ref,
        outcome_kind=outcome_kind,
        certificate_refs=certificate_refs,
        output_ref=output_ref,
        complete=complete,
    )


def commit_trace_lineage_schema(event_type: str) -> dict[str, Any]:
    contract = COMMIT_EVENT_CONTRACTS[event_type]
    properties = {
        name: _field_schema(spec)
        for name, spec in {
            **_COMMON_REQUIRED,
            **contract.required,
            **contract.optional,
        }.items()
    }
    properties["extensions"] = {
        "type": "object",
        "propertyNames": {
            "pattern": r"^(?!(?:x-critical|ext\.critical))(?:x-.+|ext\..+)$"
        },
        "additionalProperties": True,
    }
    schema: dict[str, Any] = {
        "type": "object",
        "required": sorted(commit_trace_required_fields(event_type)),
        "properties": properties,
        "additionalProperties": False,
    }
    if event_type == "commit_provisional":
        schema["allOf"] = [
            {
                "if": {
                    "properties": {"witness_count": {"const": 0}},
                    "required": ["witness_count"],
                },
                "then": {
                    "not": {
                        "anyOf": [
                            {"required": ["commit_value_root"]},
                            {"required": ["proposal_digest"]},
                        ]
                    }
                },
                "else": {
                    "required": ["commit_value_root", "proposal_digest"]
                },
            }
        ]
    return schema


def _validate_event_semantics(event_type: str, lineage: Mapping[str, Any]) -> None:
    if event_type == "commit_window_advanced":
        if lineage["required_stability_steps"] <= 0:
            raise ValueError("commit window required_stability_steps must be positive")
        if lineage["leader_candidate_id"] and lineage["stability_count"] <= 0:
            raise ValueError(
                "ready commit window stability_count must be positive"
            )
        if not lineage["leader_candidate_id"] and lineage["stability_count"] != 0:
            raise ValueError(
                "non-ready commit window stability_count must be zero"
            )
    elif event_type == "commit_window_reset":
        if lineage["reset_count"] <= 0:
            raise ValueError("commit window reset_count must be positive")
        if lineage["window_ref"] == lineage["prior_window_ref"]:
            raise ValueError("commit window reset must issue a new window state")
    elif event_type == "commit_provisional":
        if lineage["final"]:
            raise ValueError("commit_provisional trace cannot claim finality")
        if lineage["witness_count"] >= lineage["witness_quorum"]:
            raise ValueError("commit_provisional trace must remain below witness quorum")
        proposal_present = "proposal_digest" in lineage
        value_present = "commit_value_root" in lineage
        if lineage["witness_count"] == 0 and (proposal_present or value_present):
            raise ValueError(
                "zero-witness provisional trace cannot claim a proposal/value"
            )
        if lineage["witness_count"] > 0 and (
            not proposal_present or not value_present
        ):
            raise ValueError(
                "witness-bearing provisional trace requires the exact proposal/value"
            )
    elif event_type == "certificate_conflict":
        if not lineage["frozen"]:
            raise ValueError("certificate conflict trace must freeze the epoch")
        if len(lineage["commit_value_roots"]) < 2:
            raise ValueError(
                "certificate conflict trace requires distinct commit values"
            )
    elif event_type == "quorum_witness" and not lineage["verified"]:
        raise ValueError("quorum_witness trace must contain a verified witness")
    elif event_type == "commit_certificate_issued":
        if lineage["claim_fingerprint"] and _ROOT_RE.fullmatch(
            lineage["claim_fingerprint"]
        ) is None:
            raise ValueError(
                "commit certificate trace claim must be empty or a canonical root"
            )
        if lineage["certificate_kind"] != "outcome" and not (
            lineage["candidate_id"] and _ROOT_RE.fullmatch(lineage["claim_fingerprint"])
        ):
            raise ValueError(
                "commit certificate trace requires a substantive candidate and claim"
            )
        value_present = "commit_value_root" in lineage
        if (lineage["certificate_kind"] == "distributed_commit") is not value_present:
            raise ValueError(
                "distributed certificate trace must exclusively bind a commit value root"
            )
    elif event_type == "decision_outcome":
        committed = lineage["kind"] == "evidence_commit"
        if lineage["authoritative_commit"] != committed:
            raise ValueError("decision outcome authoritative_commit is inconsistent")
        if lineage["epistemically_committed"] != committed:
            raise ValueError("decision outcome epistemically_committed is inconsistent")
        if committed and "certificate_ref" not in lineage:
            raise ValueError("evidence commit outcome requires certificate_ref")
        if not committed and "certificate_ref" in lineage:
            raise ValueError("non-commit outcome cannot carry a commit certificate_ref")


def _validate_terminal_path(
    outcome_kind: str,
    by_type: Mapping[str, list[Any]],
    outcomes: list[Any],
) -> None:
    if not outcomes:
        return
    if outcome_kind == "evidence_commit":
        if not by_type.get("commit_window_advanced"):
            raise ValueError("evidence commit trace lacks a stable window")
        if not by_type.get("commit_certificate_issued"):
            raise ValueError("evidence commit trace lacks a certificate")
        outcome_certificate = outcomes[0].lineage["certificate_ref"]
        if outcome_certificate not in {
            item.lineage["certificate_ref"]
            for item in by_type["commit_certificate_issued"]
        }:
            raise ValueError("evidence commit outcome references an untraced certificate")
    elif outcome_kind == "safety_violation":
        if not by_type.get("certificate_conflict"):
            raise ValueError("safety violation trace lacks a certificate conflict")
    elif outcome_kind == "finality_unavailable":
        if not (
            by_type.get("commit_provisional") or by_type.get("quorum_pending")
        ):
            raise ValueError("finality unavailable trace lacks pending finality lineage")


def _validate_terminal_output(
    outcome_kind: str,
    outcome: Mapping[str, Any],
    output: Mapping[str, Any],
) -> None:
    if not output["deliver"]:
        raise ValueError("every terminal commit outcome must be deliverable")
    if outcome_kind != "evidence_commit" and output["execute"]:
        raise ValueError("non-commit terminal outcome cannot authorize execute")
    if outcome_kind in {
        "blocked",
        "invalid",
        "finality_unavailable",
        "safety_violation",
    } and output["publish"]:
        raise ValueError(f"{outcome_kind} cannot publish an authoritative result")
    if outcome_kind == "evidence_commit":
        certificate_ref = outcome["certificate_ref"]
        if output.get("certificate_ref") != certificate_ref:
            raise ValueError("commit output certificate does not match its outcome")


def _validate_field(event_type: str, name: str, value: Any, spec: object) -> None:
    path = f"{event_type} trace {name}"
    if spec == _TEXT:
        _require_text(value, path)
    elif spec == _STRING:
        _require_string(value, path)
    elif spec == _ROOT:
        _require_root(value, path)
    elif spec in {_STEP, _COUNT}:
        _require_integer(value, path)
    elif spec == _INTEGER:
        _require_signed_integer(value, path)
    elif spec == _BOOL:
        if type(value) is not bool:
            raise ValueError(f"{path} must be a boolean")
    elif spec == _TEXTS:
        _require_sequence(value, path, roots=False)
    elif spec == _ROOTS:
        _require_sequence(value, path, roots=True)
    elif spec == _PAYLOAD:
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be a JSON object")
    elif isinstance(spec, frozenset):
        if _enum_value(value) not in spec:
            raise ValueError(f"{path} has an unsupported value")
    else:  # pragma: no cover - contract authoring invariant
        raise AssertionError(f"unknown commit trace field specification: {spec!r}")


def _require_text(value: Any, path: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value != unicodedata.normalize("NFC", value)
    ):
        raise ValueError(f"{path} must be a canonical non-blank NFC string")


def _require_string(value: Any, path: str) -> None:
    if (
        not isinstance(value, str)
        or value != unicodedata.normalize("NFC", value)
        or (value and value != value.strip())
    ):
        raise ValueError(f"{path} must be a canonical NFC string")


def _require_root(value: Any, path: str) -> None:
    if not isinstance(value, str) or _ROOT_RE.fullmatch(value) is None:
        raise ValueError(f"{path} must be a canonical sha256 fingerprint")


def _require_integer(value: Any, path: str) -> None:
    if type(value) is not int or value < 0 or value > MAX_AUTHORITY_INTEGER:
        raise ValueError(f"{path} must be a bounded nonnegative exact integer")


def _require_signed_integer(value: Any, path: str) -> None:
    if type(value) is not int or abs(value) > MAX_AUTHORITY_INTEGER:
        raise ValueError(f"{path} must be a bounded exact integer")


def _require_sequence(value: Any, path: str, *, roots: bool) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a JSON array")
    expected = sorted(value)
    if value != expected or len(value) != len(set(value)):
        raise ValueError(f"{path} must use canonical set ordering")
    for index, item in enumerate(value):
        if roots:
            _require_root(item, f"{path}[{index}]")
        else:
            _require_text(item, f"{path}[{index}]")


def _validate_extensions(value: Any, *, event_type: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError(f"{event_type} trace extensions must be an object")
    for key in value:
        _require_text(key, f"{event_type} trace extension key")
        if key.startswith(_CRITICAL_EXTENSION_PREFIXES):
            raise ValueError(f"{event_type} trace contains an unknown critical extension")
        if _NONCRITICAL_EXTENSION_RE.fullmatch(key) is None:
            raise ValueError(f"{event_type} trace extension key must be namespaced")


def _field_schema(spec: object) -> dict[str, Any]:
    if spec == _TEXT:
        return {"type": "string", "minLength": 1}
    if spec == _STRING:
        return {"type": "string"}
    if spec == _ROOT:
        return {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"}
    if spec in {_STEP, _COUNT}:
        return {
            "type": "integer",
            "minimum": 0,
            "maximum": MAX_AUTHORITY_INTEGER,
        }
    if spec == _INTEGER:
        return {
            "type": "integer",
            "minimum": -MAX_AUTHORITY_INTEGER,
            "maximum": MAX_AUTHORITY_INTEGER,
        }
    if spec == _BOOL:
        return {"type": "boolean"}
    if spec == _TEXTS:
        return {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        }
    if spec == _ROOTS:
        return {
            "type": "array",
            "items": {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"},
            "uniqueItems": True,
        }
    if spec == _PAYLOAD:
        return {"type": "object"}
    if isinstance(spec, frozenset):
        return {"enum": sorted(spec)}
    raise AssertionError(f"unknown commit trace schema specification: {spec!r}")


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _normalize_compare(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {key: _normalize_compare(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize_compare(item) for item in value]
    return value


def _canonical_sequence(value: Any, *, spec: object) -> Any:
    del spec
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return sorted(value)
    return value


def _normalize_field_compare(value: Any, *, spec: object) -> Any:
    normalized = _normalize_compare(value)
    if spec in {_TEXTS, _ROOTS} and isinstance(normalized, list):
        return sorted(normalized)
    return normalized


def _portable_value(value: Any, *, path: str) -> Any:
    if isinstance(value, Enum):
        return _portable_value(value.value, path=path)
    if value is None or type(value) is bool:
        return value
    if isinstance(value, str):
        _require_string(value, path)
        return value
    if type(value) is int:
        _require_signed_integer(value, path)
        return value
    if isinstance(value, float):
        raise ValueError(f"{path} must not contain floating-point values")
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            _require_text(key, f"{path} key")
            normalized[key] = _portable_value(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, (tuple, list)):
        return [
            _portable_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ValueError(f"{path} contains an unsupported JSON value")


__all__ = [
    "COMMIT_EVENT_CONTRACTS",
    "COMMIT_EVENT_TYPES",
    "COMMIT_TRACE_EVENT_SCHEMA",
    "COMMIT_TRACE_PAYLOAD_VERSION",
    "CommitTraceEventContract",
    "CommitTraceReplay",
    "build_commit_trace_lineage",
    "commit_trace_event_id",
    "commit_trace_lineage_schema",
    "commit_trace_required_fields",
    "replay_commit_trace",
    "validate_commit_trace_event",
]
