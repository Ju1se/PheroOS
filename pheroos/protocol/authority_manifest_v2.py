"""Exact declaration-only contracts for the scoped-authority v2 profile."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Any
import unicodedata

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
)
from pheroos.protocol._immutable import canonical_json_snapshot
from pheroos.protocol.extensions import (
    collect_extensions,
    is_namespaced_extension,
    reject_secret_like_fields,
)
from pheroos.protocol.manifest import (
    candidate_from_dict,
    collective_commit_policy_from_dict,
    collective_decision_policy_from_dict,
    driver_from_dict,
    evidence_policy_from_dict,
    recovery_from_dict,
    signal_from_dict,
    target_from_dict,
    trace_policy_from_dict,
)
from pheroos.protocol.models import (
    CandidateSpec,
    CollectiveDecisionPolicy,
    DriverSpec,
    EvidencePolicy,
    QuorumPolicy,
    RecoveryProtocol,
    SignalSpec,
    TargetSpec,
    TracePolicy,
)
from pheroos.protocol.commit_models import CollectiveCommitPolicy


PROTOCOL_VERSION_V2 = "pheroos.protocol.v2"
BASELINE_OUTPUT_POLICY_VERSION_V2 = "pheroos-baseline-output-policy-v2"

AUTHORITY_POLICY_VERSION_V2 = "pheroos-scoped-authority-policy-v2"
AUTHORITY_LOCAL_PROFILE_V2 = "pheroos-scoped-authority-local-v2"
AUTHORITY_AUTHENTICATED_PROFILE_V2 = "pheroos-scoped-authority-authenticated-v2"
AUTHORITY_WIRE_VERSION_V2 = "pheroos-authority-wire-v2"
AUTHORITY_LEDGER_VERSION_V2 = "pheroos-governance-authority-ledger-v2"
GOVERNANCE_STATE_STORE_VERSION_V2 = "pheroos-governance-state-store-v2"
GOVERNANCE_TRACE_BATCH_VERSION_V2 = "pheroos-governance-trace-batch-v2"

SUPPORTED_AUTHORITY_PROFILES_V2 = frozenset(
    {AUTHORITY_LOCAL_PROFILE_V2, AUTHORITY_AUTHENTICATED_PROFILE_V2}
)
SUPPORTED_BASELINE_OUTPUT_EFFECTS_V2 = frozenset({"publish", "execute"})
SUPPORTED_BASELINE_ACTION_OUTCOMES_V2 = frozenset({"evidence_commit", "safe_fallback"})
SUPPORTED_BASELINE_DECISION_MODES_V2 = frozenset({"quorum", "direct_governance"})
REQUIRED_BASELINE_OUTPUT_TRACE_EVENTS_V2 = frozenset(
    {
        "baseline_manifest_activated",
        "baseline_evidence_qualified",
        "baseline_stop_resolved",
        "baseline_decision_evaluated",
        "baseline_action_permission_issued",
        "baseline_output_committed",
    }
)

_AUTHORITY_POLICY_FIELDS = frozenset(
    {
        "policy_version",
        "profile",
        "wire_version",
        "canonical_version",
        "ledger_version",
        "state_store_version",
        "trace_batch_version",
        "read_set_version",
    }
)
_OUTPUT_ACTION_FIELDS = frozenset(
    {"action_ref", "effect", "target", "allowed_outcomes"}
)
_OUTPUT_POLICY_FIELDS = frozenset({"policy_version", "decision_mode", "actions"})
_PROTOCOL_REQUIRED_FIELDS = frozenset(
    {
        "protocol_version",
        "id",
        "targets",
        "candidates",
        "quorum_policy",
        "authority_policy",
        "output_policy",
        "trace_policy",
    }
)
_PROTOCOL_OPTIONAL_FIELDS = frozenset(
    {
        "signals",
        "collective_decision_policy",
        "collective_commit_policy",
        "recovery_protocols",
        "evidence_policy",
        "extensions",
    }
)
_CAPABILITY_REQUIRED_FIELDS = frozenset({"id", "name", "version", "protocol"})
_CAPABILITY_OPTIONAL_FIELDS = frozenset(
    {"permissions", "required_connections", "drivers", "extensions"}
)
_QUORUM_FIELDS = frozenset(
    {"target", "fallback_candidate", "commit_threshold", "extensions"}
)
_MAX_OUTPUT_ACTIONS = 128
_ROOT_PREFIX = b"pheroos-protocol-scoped-manifest-v2:"


class ScopedManifestV2Error(ValueError):
    """A scoped v2 manifest declaration is malformed or noncanonical."""


class _CanonicalDeclarationV2(ABC):
    __slots__ = ()

    @abstractmethod
    def to_dict(self) -> dict[str, object]: ...

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def root(self) -> str:
        kind = type(self).__name__.encode("ascii")
        digest = sha256(_ROOT_PREFIX + kind + b"\x00" + self.canonical_bytes())
        return "sha256:" + digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ScopedAuthorityPolicyV2(_CanonicalDeclarationV2):
    policy_version: str
    profile: str
    wire_version: str
    canonical_version: str
    ledger_version: str
    state_store_version: str
    trace_batch_version: str
    read_set_version: str

    def __post_init__(self) -> None:
        expected = {
            "policy_version": AUTHORITY_POLICY_VERSION_V2,
            "wire_version": AUTHORITY_WIRE_VERSION_V2,
            "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
            "ledger_version": AUTHORITY_LEDGER_VERSION_V2,
            "state_store_version": GOVERNANCE_STATE_STORE_VERSION_V2,
            "trace_batch_version": GOVERNANCE_TRACE_BATCH_VERSION_V2,
            "read_set_version": GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        }
        for name, exact in expected.items():
            if getattr(self, name) != exact:
                raise ScopedManifestV2Error(f"scoped authority {name} is unsupported")
        if self.profile not in SUPPORTED_AUTHORITY_PROFILES_V2:
            raise ScopedManifestV2Error("scoped authority profile is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "profile": self.profile,
            "wire_version": self.wire_version,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "state_store_version": self.state_store_version,
            "trace_batch_version": self.trace_batch_version,
            "read_set_version": self.read_set_version,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ScopedAuthorityPolicyV2:
        value = _exact_object(
            payload,
            expected_fields=_AUTHORITY_POLICY_FIELDS,
            label="scoped authority policy",
        )
        return cls(**value)


@dataclass(frozen=True, slots=True)
class BaselineOutputActionPolicyV2(_CanonicalDeclarationV2):
    action_ref: str
    effect: str
    target: str
    allowed_outcomes: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.action_ref, "baseline output action_ref")
        _require_text(self.target, "baseline output target")
        if self.effect not in SUPPORTED_BASELINE_OUTPUT_EFFECTS_V2:
            raise ScopedManifestV2Error("baseline output effect is unsupported")
        _require_sorted_text_tuple(
            self.allowed_outcomes,
            "baseline output allowed_outcomes",
            allow_empty=False,
        )
        if not set(self.allowed_outcomes).issubset(
            SUPPORTED_BASELINE_ACTION_OUTCOMES_V2
        ):
            raise ScopedManifestV2Error(
                "baseline output allowed_outcomes contains a non-actionable status"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "action_ref": self.action_ref,
            "effect": self.effect,
            "target": self.target,
            "allowed_outcomes": list(self.allowed_outcomes),
        }

    @classmethod
    def from_dict(cls, payload: object) -> BaselineOutputActionPolicyV2:
        value = _exact_object(
            payload,
            expected_fields=_OUTPUT_ACTION_FIELDS,
            label="baseline output action policy",
        )
        outcomes = value["allowed_outcomes"]
        if type(outcomes) is not list:
            raise ScopedManifestV2Error(
                "baseline output allowed_outcomes must be an array"
            )
        return cls(
            action_ref=value["action_ref"],
            effect=value["effect"],
            target=value["target"],
            allowed_outcomes=tuple(outcomes),
        )


@dataclass(frozen=True, slots=True)
class BaselineOutputPolicyV2(_CanonicalDeclarationV2):
    policy_version: str
    decision_mode: str
    actions: tuple[BaselineOutputActionPolicyV2, ...]

    def __post_init__(self) -> None:
        if self.policy_version != BASELINE_OUTPUT_POLICY_VERSION_V2:
            raise ScopedManifestV2Error("baseline output policy_version is unsupported")
        if self.decision_mode not in SUPPORTED_BASELINE_DECISION_MODES_V2:
            raise ScopedManifestV2Error("baseline output decision_mode is unsupported")
        if type(self.actions) is not tuple or len(self.actions) > _MAX_OUTPUT_ACTIONS:
            raise ScopedManifestV2Error(
                "baseline output actions must be a tuple with at most 128 items"
            )
        if any(type(item) is not BaselineOutputActionPolicyV2 for item in self.actions):
            raise ScopedManifestV2Error(
                "baseline output actions must use the canonical action policy"
            )
        action_keys = tuple(item.action_ref.encode("utf-8") for item in self.actions)
        if len(set(action_keys)) != len(action_keys):
            raise ScopedManifestV2Error(
                "baseline output action_ref values must be unique"
            )
        if action_keys != tuple(sorted(action_keys)):
            raise ScopedManifestV2Error(
                "baseline output actions must use unsigned UTF-8 action_ref order"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "decision_mode": self.decision_mode,
            "actions": [item.to_dict() for item in self.actions],
        }

    @property
    def policy_root(self) -> str:
        """Return the exact canonical policy root used by Governance bindings."""

        return self.root()

    @classmethod
    def from_dict(cls, payload: object) -> BaselineOutputPolicyV2:
        value = _exact_object(
            payload,
            expected_fields=_OUTPUT_POLICY_FIELDS,
            label="baseline output policy",
        )
        actions = value["actions"]
        if type(actions) is not list:
            raise ScopedManifestV2Error("baseline output actions must be an array")
        return cls(
            policy_version=value["policy_version"],
            decision_mode=value["decision_mode"],
            actions=tuple(
                BaselineOutputActionPolicyV2.from_dict(item) for item in actions
            ),
        )


@dataclass(frozen=True, slots=True)
class ScopedProtocolManifestV2(_CanonicalDeclarationV2):
    protocol_version: str
    id: str
    targets: tuple[TargetSpec, ...]
    candidates: tuple[CandidateSpec, ...]
    quorum_policy: QuorumPolicy
    authority_policy: ScopedAuthorityPolicyV2
    output_policy: BaselineOutputPolicyV2
    trace_policy: TracePolicy
    evidence_policy: EvidencePolicy
    signals: tuple[SignalSpec, ...] = ()
    recovery_protocols: tuple[RecoveryProtocol, ...] = ()
    collective_decision_policy: CollectiveDecisionPolicy | None = None
    collective_commit_policy: CollectiveCommitPolicy | None = None
    extensions: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION_V2:
            raise ScopedManifestV2Error("scoped protocol version is unsupported")
        _require_text(self.id, "scoped protocol id")
        _require_exact_tuple(self.targets, TargetSpec, "scoped protocol targets")
        _require_exact_tuple(
            self.candidates, CandidateSpec, "scoped protocol candidates"
        )
        _require_exact_tuple(self.signals, SignalSpec, "scoped protocol signals")
        _require_exact_tuple(
            self.recovery_protocols,
            RecoveryProtocol,
            "scoped protocol recovery_protocols",
        )
        if type(self.quorum_policy) is not QuorumPolicy:
            raise ScopedManifestV2Error(
                "scoped protocol quorum_policy must use the canonical declaration"
            )
        if type(self.authority_policy) is not ScopedAuthorityPolicyV2:
            raise ScopedManifestV2Error(
                "scoped protocol authority_policy must use the canonical declaration"
            )
        if type(self.output_policy) is not BaselineOutputPolicyV2:
            raise ScopedManifestV2Error(
                "scoped protocol output_policy must use the canonical declaration"
            )
        if type(self.trace_policy) is not TracePolicy:
            raise ScopedManifestV2Error(
                "scoped protocol trace_policy must use the canonical declaration"
            )
        if type(self.evidence_policy) is not EvidencePolicy:
            raise ScopedManifestV2Error(
                "scoped protocol evidence_policy must use the canonical declaration"
            )
        _validate_text_tree(self)
        _validate_protocol_declarations(self)
        object.__setattr__(self, "extensions", _freeze_mapping(self.extensions))

    def to_dict(self) -> dict[str, object]:
        body: dict[str, object] = {
            "protocol_version": self.protocol_version,
            "id": self.id,
            "targets": [_portable(item) for item in self.targets],
            "candidates": [_portable(item) for item in self.candidates],
            "signals": [_portable(item) for item in self.signals],
            "quorum_policy": _portable(self.quorum_policy),
            "authority_policy": self.authority_policy.to_dict(),
            "recovery_protocols": [_portable(item) for item in self.recovery_protocols],
            "evidence_policy": _portable(self.evidence_policy),
            "output_policy": self.output_policy.to_dict(),
            "trace_policy": _portable(self.trace_policy),
            "extensions": _portable(self.extensions),
        }
        if self.collective_decision_policy is not None:
            body["collective_decision_policy"] = _portable(
                self.collective_decision_policy
            )
        if self.collective_commit_policy is not None:
            body["collective_commit_policy"] = _portable(self.collective_commit_policy)
        return body

    @property
    def manifest_root(self) -> str:
        """Return the exact canonical Protocol manifest root."""

        return self.root()

    @classmethod
    def from_dict(cls, payload: object) -> ScopedProtocolManifestV2:
        return scoped_protocol_manifest_v2_from_dict(payload)


@dataclass(frozen=True, slots=True)
class ScopedCapabilityManifestV2(_CanonicalDeclarationV2):
    id: str
    name: str
    version: str
    protocol: ScopedProtocolManifestV2
    permissions: tuple[str, ...] = ()
    required_connections: tuple[str, ...] = ()
    drivers: tuple[DriverSpec, ...] = ()
    extensions: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        _require_text(self.id, "scoped capability id")
        _require_text(self.name, "scoped capability name")
        _require_text(self.version, "scoped capability version")
        if type(self.protocol) is not ScopedProtocolManifestV2:
            raise ScopedManifestV2Error(
                "scoped capability protocol must use the exact v2 manifest type"
            )
        _require_text_tuple(self.permissions, "scoped capability permissions")
        _require_text_tuple(
            self.required_connections,
            "scoped capability required_connections",
        )
        _require_exact_tuple(self.drivers, DriverSpec, "scoped capability drivers")
        _validate_text_tree(self)
        object.__setattr__(self, "extensions", _freeze_mapping(self.extensions))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "permissions": list(self.permissions),
            "required_connections": list(self.required_connections),
            "drivers": [_portable(item) for item in self.drivers],
            "protocol": self.protocol.to_dict(),
            "extensions": _portable(self.extensions),
        }

    @property
    def manifest_root(self) -> str:
        """Return the exact canonical Capability manifest root."""

        return self.root()

    @classmethod
    def from_dict(cls, payload: object) -> ScopedCapabilityManifestV2:
        return scoped_capability_manifest_v2_from_dict(payload)


def scoped_protocol_manifest_v2_from_dict(
    payload: object,
) -> ScopedProtocolManifestV2:
    value = _manifest_object(
        payload,
        required=_PROTOCOL_REQUIRED_FIELDS,
        optional=_PROTOCOL_OPTIONAL_FIELDS,
        label="scoped protocol manifest",
    )
    reject_secret_like_fields(value)
    _validate_text_tree(value)
    quorum = _quorum_policy_from_dict(value["quorum_policy"])
    return ScopedProtocolManifestV2(
        protocol_version=_required_text(value, "protocol_version"),
        id=_required_text(value, "id"),
        targets=tuple(target_from_dict(item) for item in _array(value, "targets")),
        candidates=tuple(
            candidate_from_dict(item) for item in _array(value, "candidates")
        ),
        quorum_policy=quorum,
        authority_policy=ScopedAuthorityPolicyV2.from_dict(value["authority_policy"]),
        output_policy=BaselineOutputPolicyV2.from_dict(value["output_policy"]),
        trace_policy=trace_policy_from_dict(_object(value["trace_policy"])),
        evidence_policy=evidence_policy_from_dict(
            _object(value.get("evidence_policy", {}))
        ),
        signals=tuple(
            signal_from_dict(item) for item in _array(value, "signals", default=[])
        ),
        recovery_protocols=tuple(
            recovery_from_dict(item)
            for item in _array(value, "recovery_protocols", default=[])
        ),
        collective_decision_policy=collective_decision_policy_from_dict(
            value.get("collective_decision_policy")
        ),
        collective_commit_policy=collective_commit_policy_from_dict(
            value.get("collective_commit_policy")
        ),
        extensions=collect_extensions(value),
    )


def scoped_capability_manifest_v2_from_dict(
    payload: object,
) -> ScopedCapabilityManifestV2:
    value = _manifest_object(
        payload,
        required=_CAPABILITY_REQUIRED_FIELDS,
        optional=_CAPABILITY_OPTIONAL_FIELDS,
        label="scoped capability manifest",
    )
    reject_secret_like_fields(value)
    _validate_text_tree(value)
    return ScopedCapabilityManifestV2(
        id=_required_text(value, "id"),
        name=_required_text(value, "name"),
        version=_required_text(value, "version"),
        permissions=tuple(_text_array(value, "permissions", default=[])),
        required_connections=tuple(
            _text_array(value, "required_connections", default=[])
        ),
        drivers=tuple(
            driver_from_dict(item) for item in _array(value, "drivers", default=[])
        ),
        protocol=scoped_protocol_manifest_v2_from_dict(value["protocol"]),
        extensions=collect_extensions(value),
    )


def _quorum_policy_from_dict(payload: object) -> QuorumPolicy:
    value = _manifest_object(
        payload,
        required=frozenset({"target", "fallback_candidate"}),
        optional=frozenset({"commit_threshold", "extensions"}),
        label="scoped quorum policy",
    )
    threshold = value.get("commit_threshold", 1)
    if type(threshold) is not int or threshold < 1:
        raise ScopedManifestV2Error(
            "scoped quorum commit_threshold must be a positive exact integer"
        )
    return QuorumPolicy(
        target=_required_text(value, "target"),
        fallback_candidate=_required_text(value, "fallback_candidate"),
        commit_threshold=threshold,
        extensions=collect_extensions(value),
    )


def _validate_protocol_declarations(manifest: ScopedProtocolManifestV2) -> None:
    if not manifest.targets or not manifest.candidates:
        raise ScopedManifestV2Error(
            "scoped protocol must declare targets and candidates"
        )
    target_ids = tuple(_require_text(item.id, "target id") for item in manifest.targets)
    candidate_ids = tuple(
        _require_text(item.id, "candidate id") for item in manifest.candidates
    )
    _require_unique(target_ids, "scoped protocol target ids")
    _require_unique(candidate_ids, "scoped protocol candidate ids")
    _validate_signal_declarations(manifest, target_ids)
    _validate_recovery_declarations(manifest, target_ids)
    _validate_candidate_declarations(manifest, target_ids)
    _validate_collective_cross_references(manifest)
    _validate_output_action_targets(manifest, target_ids)
    _validate_baseline_safety_policy(manifest)


def _validate_signal_declarations(
    manifest: ScopedProtocolManifestV2,
    target_ids: tuple[str, ...],
) -> None:
    for signal in manifest.signals:
        _require_text(signal.type, "signal type")
        _require_text(signal.target, "signal target")
        _require_text(signal.authority_required, "signal authority_required")
        if signal.target not in target_ids:
            raise ScopedManifestV2Error("scoped signal target must be declared")


def _validate_recovery_declarations(
    manifest: ScopedProtocolManifestV2,
    target_ids: tuple[str, ...],
) -> None:
    recovery_ids = tuple(
        _require_text(item.id, "recovery protocol id")
        for item in manifest.recovery_protocols
    )
    _require_unique(recovery_ids, "scoped recovery protocol ids")
    candidates = {item.id: item for item in manifest.candidates}
    for recovery in manifest.recovery_protocols:
        for target in recovery.trigger_targets:
            _require_text(target, "recovery trigger target")
            if target not in target_ids:
                raise ScopedManifestV2Error(
                    "scoped recovery trigger target must be declared"
                )
        if recovery.failure_candidate:
            _require_text(recovery.failure_candidate, "recovery failure candidate")
            candidate = candidates.get(recovery.failure_candidate)
            if candidate is None:
                raise ScopedManifestV2Error(
                    "scoped recovery failure candidate must be declared"
                )
            if candidate.target not in recovery.trigger_targets:
                raise ScopedManifestV2Error(
                    "scoped recovery failure candidate must target a trigger target"
                )


def _validate_candidate_declarations(
    manifest: ScopedProtocolManifestV2, target_ids: tuple[str, ...]
) -> None:
    _require_text(manifest.quorum_policy.target, "quorum target")
    _require_text(
        manifest.quorum_policy.fallback_candidate,
        "quorum fallback candidate",
    )
    if (
        type(manifest.quorum_policy.commit_threshold) is not int
        or manifest.quorum_policy.commit_threshold < 1
    ):
        raise ScopedManifestV2Error(
            "scoped quorum commit_threshold must be a positive exact integer"
        )
    if manifest.quorum_policy.target not in target_ids:
        raise ScopedManifestV2Error("scoped quorum target must be declared")
    candidates = {item.id: item for item in manifest.candidates}
    for candidate in manifest.candidates:
        _require_text(candidate.target, "candidate target")
        if type(candidate.safe_fallback) is not bool:
            raise ScopedManifestV2Error(
                "scoped candidate safe_fallback must be an exact boolean"
            )
        if candidate.target not in target_ids:
            raise ScopedManifestV2Error("scoped candidate target must be declared")
    fallback = candidates.get(manifest.quorum_policy.fallback_candidate)
    if (
        fallback is None
        or fallback.safe_fallback is not True
        or fallback.target != manifest.quorum_policy.target
    ):
        raise ScopedManifestV2Error(
            "scoped quorum fallback must be a safe declared candidate for its target"
        )


def _validate_collective_cross_references(
    manifest: ScopedProtocolManifestV2,
) -> None:
    candidates = {item.id: item for item in manifest.candidates}
    collective = manifest.collective_decision_policy
    if collective is not None:
        if type(collective) is not CollectiveDecisionPolicy:
            raise ScopedManifestV2Error(
                "scoped collective decision policy must use the canonical declaration"
            )
        fallback_id = (
            collective.fallback_candidate or manifest.quorum_policy.fallback_candidate
        )
        fallback = candidates.get(fallback_id)
        if (
            fallback is None
            or fallback.safe_fallback is not True
            or fallback.target != manifest.quorum_policy.target
        ):
            raise ScopedManifestV2Error(
                "scoped collective fallback must be a safe declared candidate "
                "for the quorum target"
            )

    commit = manifest.collective_commit_policy
    if commit is None:
        return
    if type(commit) is not CollectiveCommitPolicy:
        raise ScopedManifestV2Error(
            "scoped collective commit policy must use the canonical declaration"
        )
    if commit.target != manifest.quorum_policy.target:
        raise ScopedManifestV2Error(
            "scoped collective commit target must match the quorum target"
        )
    fallback_id = commit.terminal_outcome.safe_fallback_candidate
    expected_fallback = manifest.quorum_policy.fallback_candidate
    if collective is not None:
        expected_fallback = collective.fallback_candidate or expected_fallback
    if fallback_id != expected_fallback:
        raise ScopedManifestV2Error(
            "scoped collective commit fallback must match quorum and collective fallback"
        )
    # Candidate safety and target binding were already established by the quorum
    # and optional collective-decision checks above.  Exact fallback identity is
    # the only additional invariant owned by the commit declaration.


def _validate_output_action_targets(
    manifest: ScopedProtocolManifestV2, target_ids: tuple[str, ...]
) -> None:
    for action in manifest.output_policy.actions:
        if action.target not in target_ids:
            raise ScopedManifestV2Error(
                "baseline output action target must be declared"
            )
        if action.target != manifest.quorum_policy.target:
            raise ScopedManifestV2Error(
                "baseline output actions must use the quorum fallback target"
            )


def _validate_baseline_safety_policy(manifest: ScopedProtocolManifestV2) -> None:
    if manifest.evidence_policy.require_provenance is not True:
        raise ScopedManifestV2Error(
            "scoped baseline output requires evidence provenance"
        )
    if manifest.evidence_policy.allow_agent_fact_creation is not False:
        raise ScopedManifestV2Error(
            "scoped baseline output forbids agent fact creation"
        )
    missing_trace = REQUIRED_BASELINE_OUTPUT_TRACE_EVENTS_V2 - set(
        manifest.trace_policy.required_events
    )
    if missing_trace:
        raise ScopedManifestV2Error(
            "scoped baseline output trace policy is missing required events: "
            + ", ".join(sorted(missing_trace))
        )


def _manifest_object(
    payload: object,
    *,
    required: frozenset[str],
    optional: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(payload) is not dict:
        raise ScopedManifestV2Error(f"{label} must be an exact JSON object")
    value = payload
    missing = required - set(value)
    unknown = {
        key
        for key in set(value) - required - optional
        if not is_namespaced_extension(str(key))
    }
    if missing or unknown:
        raise ScopedManifestV2Error(
            f"{label} fields are invalid: missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )
    return value


def _exact_object(
    payload: object,
    *,
    expected_fields: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(payload) is not dict or set(payload) != expected_fields:
        observed = set(payload) if type(payload) is dict else set()
        raise ScopedManifestV2Error(
            f"{label} fields are invalid: "
            f"missing={sorted(expected_fields - observed)}, "
            f"unknown={sorted(observed - expected_fields)}"
        )
    return payload


def _object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ScopedManifestV2Error("scoped manifest field must be an object")
    return value


def _array(
    payload: dict[str, Any],
    key: str,
    *,
    default: list[Any] | None = None,
) -> list[Any]:
    value = payload.get(key, default)
    if type(value) is not list:
        raise ScopedManifestV2Error(f"scoped manifest {key} must be an array")
    return value


def _text_array(
    payload: dict[str, Any],
    key: str,
    *,
    default: list[str],
) -> list[str]:
    value = _array(payload, key, default=default)
    if any(type(item) is not str for item in value):
        raise ScopedManifestV2Error(f"scoped manifest {key} must contain strings")
    return value


def _required_text(payload: dict[str, Any], key: str) -> str:
    # Every caller receives ``payload`` from _manifest_object with ``key`` in
    # its required set, so a second runtime missing-field branch is redundant.
    return _require_text(payload[key], f"scoped manifest {key}")


def _require_text(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ScopedManifestV2Error(f"{label} must be canonical non-blank text")
    if unicodedata.normalize("NFC", value) != value:
        raise ScopedManifestV2Error(f"{label} must already use Unicode NFC")
    if "\x00" in value:
        raise ScopedManifestV2Error(f"{label} must not contain U+0000")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ScopedManifestV2Error(f"{label} must encode as UTF-8") from exc
    return value


def _require_sorted_text_tuple(
    value: object,
    label: str,
    *,
    allow_empty: bool,
) -> None:
    _require_text_tuple(value, label)
    assert type(value) is tuple
    if not allow_empty and not value:
        raise ScopedManifestV2Error(f"{label} must not be empty")
    keys = tuple(item.encode("utf-8") for item in value)
    if len(set(keys)) != len(keys) or keys != tuple(sorted(keys)):
        raise ScopedManifestV2Error(
            f"{label} must be unique and use unsigned UTF-8 order"
        )


def _require_text_tuple(value: object, label: str) -> None:
    if type(value) is not tuple:
        raise ScopedManifestV2Error(f"{label} must be an immutable tuple")
    for item in value:
        _require_text(item, label)


def _require_exact_tuple(
    value: object,
    expected_type: type[object],
    label: str,
) -> None:
    if type(value) is not tuple or any(
        type(item) is not expected_type for item in value
    ):
        raise ScopedManifestV2Error(
            f"{label} must be a tuple of exact {expected_type.__name__} values"
        )


def _require_unique(values: Sequence[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ScopedManifestV2Error(f"{label} must be unique")


def _validate_text_tree(value: object) -> None:
    if type(value) is str:
        _validate_tree_text(value)
        return
    if isinstance(value, Enum):
        _validate_text_tree(value.value)
        return
    if is_dataclass(value):
        for item in fields(value):
            _validate_text_tree(getattr(value, item.name))
        return
    if isinstance(value, Mapping):
        _validate_tree_mapping(value)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        _validate_tree_sequence(value)
        return
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is float and math.isfinite(value):
        return
    raise ScopedManifestV2Error(
        "scoped manifest values must use canonical JSON scalar or container types"
    )


def _validate_tree_text(value: str) -> None:
    if (
        value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or "\x00" in value
    ):
        raise ScopedManifestV2Error(
            "scoped manifest strings must use NFC without surrounding whitespace "
            "or U+0000"
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ScopedManifestV2Error(
            "scoped manifest strings must encode as UTF-8"
        ) from exc


def _validate_tree_mapping(value: Mapping[object, object]) -> None:
    if type(value) not in {dict, MappingProxyType}:
        raise ScopedManifestV2Error(
            "scoped manifest mappings must use an exact dict or mappingproxy"
        )
    for key, item in value.items():
        if type(key) is not str or not key:
            raise ScopedManifestV2Error(
                "scoped manifest mapping keys must be exact non-empty strings"
            )
        _validate_text_tree(key)
        _validate_text_tree(item)


def _validate_tree_sequence(value: Sequence[object]) -> None:
    if type(value) not in {list, tuple}:
        raise ScopedManifestV2Error(
            "scoped manifest sequences must use an exact list or tuple"
        )
    for item in value:
        _validate_text_tree(item)


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if type(value) not in {dict, MappingProxyType}:
        raise ScopedManifestV2Error(
            "scoped manifest mappings must use an exact dict or mappingproxy"
        )
    return MappingProxyType(
        {key: canonical_json_snapshot(item) for key, item in value.items()}
    )


def _portable(value: object) -> Any:
    if isinstance(value, Enum):
        return _portable(value.value)
    if is_dataclass(value):
        return {
            item.name: _portable(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
        # Construction recursively validates exact string keys before any
        # scoped declaration becomes observable.
        return {key: _portable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    return value


__all__ = [
    "BASELINE_OUTPUT_POLICY_VERSION_V2",
    "PROTOCOL_VERSION_V2",
    "BaselineOutputActionPolicyV2",
    "BaselineOutputPolicyV2",
    "ScopedAuthorityPolicyV2",
    "ScopedCapabilityManifestV2",
    "ScopedManifestV2Error",
    "ScopedProtocolManifestV2",
]
