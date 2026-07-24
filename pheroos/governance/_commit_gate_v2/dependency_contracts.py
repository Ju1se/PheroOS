"""Portable upstream authority commitments consumed by Commit Gate v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, TypedDict, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _require_root,
)
from pheroos.governance._commit_gate_v2.common import (
    COMMIT_GATE_CONTEXT_VERSION_V2,
    COMMIT_GATE_DEPENDENCIES_SCHEMA_V2,
    COMMIT_PERMISSION_POLICY_VERSION_V2,
    COMMIT_STOP_POLICY_VERSION_V2,
    _canonical_roots,
    _canonical_texts,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_exact_mapping,
    _require_profile,
    _require_text,
    _root,
)


_DEPENDENCY_NAMES = ("replay", "risk", "verification", "membership", "support")
_DEPENDENCY_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "replay_stream_ref",
        "replay_revision",
        "replay_transition_id",
        "replay_snapshot_root",
        "replay_head_root",
        "risk_stream_ref",
        "risk_revision",
        "risk_transition_id",
        "risk_snapshot_root",
        "risk_head_root",
        "verification_stream_ref",
        "verification_revision",
        "verification_transition_id",
        "verification_snapshot_root",
        "verification_head_root",
        "membership_stream_ref",
        "membership_revision",
        "membership_transition_id",
        "membership_snapshot_root",
        "membership_head_root",
        "support_stream_ref",
        "support_revision",
        "support_transition_id",
        "support_snapshot_root",
        "support_head_root",
        "dependency_root",
    }
)


class _CommitGateDependenciesDecodedV2(TypedDict):
    schema: str
    canonical_version: str
    replay_stream_ref: str
    replay_revision: int
    replay_transition_id: str
    replay_snapshot_root: str
    replay_head_root: str
    risk_stream_ref: str
    risk_revision: int
    risk_transition_id: str
    risk_snapshot_root: str
    risk_head_root: str
    verification_stream_ref: str
    verification_revision: int
    verification_transition_id: str
    verification_snapshot_root: str
    verification_head_root: str
    membership_stream_ref: str
    membership_revision: int
    membership_transition_id: str
    membership_snapshot_root: str
    membership_head_root: str
    support_stream_ref: str
    support_revision: int
    support_transition_id: str
    support_snapshot_root: str
    support_head_root: str
    dependency_root: str


@dataclass(frozen=True, slots=True)
class CommitGateDependenciesV2:
    """Portable commitment to five independently durable current heads."""

    replay_stream_ref: str
    replay_revision: int
    replay_transition_id: str
    replay_snapshot_root: str
    replay_head_root: str
    risk_stream_ref: str
    risk_revision: int
    risk_transition_id: str
    risk_snapshot_root: str
    risk_head_root: str
    verification_stream_ref: str
    verification_revision: int
    verification_transition_id: str
    verification_snapshot_root: str
    verification_head_root: str
    membership_stream_ref: str
    membership_revision: int
    membership_transition_id: str
    membership_snapshot_root: str
    membership_head_root: str
    support_stream_ref: str
    support_revision: int
    support_transition_id: str
    support_snapshot_root: str
    support_head_root: str
    schema: str = COMMIT_GATE_DEPENDENCIES_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    dependency_root: str = ""

    _root_field: ClassVar[str] = "dependency_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_GATE_DEPENDENCIES_SCHEMA_V2:
            raise ValueError("commit gate dependency schema is unsupported")
        if self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2:
            raise ValueError("commit gate dependency canonical version is unsupported")
        streams = []
        for name in _DEPENDENCY_NAMES:
            stream = _require_text(
                getattr(self, f"{name}_stream_ref"),
                f"commit gate {name} stream_ref",
            )
            streams.append(stream)
            _require_count(
                getattr(self, f"{name}_revision"),
                f"commit gate {name} revision",
                minimum=1,
            )
            _require_text(
                getattr(self, f"{name}_transition_id"),
                f"commit gate {name} transition_id",
            )
            _require_root(
                getattr(self, f"{name}_snapshot_root"),
                f"commit gate {name} snapshot_root",
            )
            _require_root(
                getattr(self, f"{name}_head_root"),
                f"commit gate {name} head_root",
            )
        if len(streams) != len(set(streams)):
            raise ValueError("commit gate dependency streams must be distinct")
        _install_root(
            self,
            "dependency_root",
            self.dependency_root,
            "dependencies",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
        }
        for name in _DEPENDENCY_NAMES:
            for suffix in (
                "stream_ref",
                "revision",
                "transition_id",
                "snapshot_root",
                "head_root",
            ):
                body[f"{name}_{suffix}"] = getattr(self, f"{name}_{suffix}")
        return body

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "dependency_root": self.dependency_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.dependency_root

    @classmethod
    def from_dict(cls, payload: object) -> CommitGateDependenciesV2:
        value = _require_exact_mapping(
            payload, _DEPENDENCY_FIELDS, "commit gate dependencies v2"
        )
        decoded = cls(**cast(_CommitGateDependenciesDecodedV2, value))
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit gate dependencies v2"
        )
        return decoded


def commit_gate_evaluation_context_root_v2(
    *,
    domain_root: str,
    scope_ref: str,
    manifest_root: str,
    commit_policy_root: str,
    profile: str,
    assurance: CommitAssurance,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
    observed_epoch: int,
    current_step: int,
    dependencies: CommitGateDependenciesV2,
) -> str:
    """Derive the common Stop/Permission evaluation context."""

    for label, value in (
        ("domain_root", domain_root),
        ("manifest_root", manifest_root),
        ("commit_policy_root", commit_policy_root),
    ):
        _require_root(value, f"commit gate context {label}")
    for label, value in (
        ("scope_ref", scope_ref),
        ("protocol_ref", protocol_ref),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
    ):
        _require_text(value, f"commit gate context {label}")
    _require_profile(profile, assurance, "commit gate context")
    _require_count(observed_epoch, "commit gate context observed_epoch")
    _require_count(current_step, "commit gate context current_step")
    if type(dependencies) is not CommitGateDependenciesV2:
        raise TypeError("commit gate context requires exact dependencies v2")
    return _root(
        "evaluation-context",
        {
            "version": COMMIT_GATE_CONTEXT_VERSION_V2,
            "domain_root": domain_root,
            "scope_ref": scope_ref,
            "manifest_root": manifest_root,
            "commit_policy_root": commit_policy_root,
            "profile": profile,
            "assurance": assurance.value,
            "protocol_ref": protocol_ref,
            "run_ref": run_ref,
            "target_ref": target_ref,
            "observed_epoch": observed_epoch,
            "current_step": current_step,
            "dependency_root": dependencies.dependency_root,
        },
    )


def commit_stop_policy_root_v2(
    *,
    manifest_root: str,
    commit_policy_root: str,
    protocol_ref: str,
    target_ref: str,
) -> str:
    return _gate_policy_root(
        "stop-policy",
        COMMIT_STOP_POLICY_VERSION_V2,
        "resolve_stop",
        manifest_root,
        commit_policy_root,
        protocol_ref,
        target_ref,
    )


def commit_permission_policy_root_v2(
    *,
    manifest_root: str,
    commit_policy_root: str,
    protocol_ref: str,
    target_ref: str,
) -> str:
    return _gate_policy_root(
        "permission-policy",
        COMMIT_PERMISSION_POLICY_VERSION_V2,
        "issue_action_permission",
        manifest_root,
        commit_policy_root,
        protocol_ref,
        target_ref,
    )


def _gate_policy_root(
    kind: str,
    version: str,
    operation: str,
    manifest_root: str,
    commit_policy_root: str,
    protocol_ref: str,
    target_ref: str,
) -> str:
    _require_root(manifest_root, f"commit gate {kind} manifest_root")
    _require_root(commit_policy_root, f"commit gate {kind} commit_policy_root")
    _require_text(protocol_ref, f"commit gate {kind} protocol_ref")
    _require_text(target_ref, f"commit gate {kind} target_ref")
    return _root(
        kind,
        {
            "policy_version": version,
            "authority_operation": operation,
            "manifest_root": manifest_root,
            "commit_policy_root": commit_policy_root,
            "protocol_ref": protocol_ref,
            "target_ref": target_ref,
        },
    )


def commit_gate_candidate_set_root_v2(candidate_refs: tuple[str, ...]) -> str:
    canonical = _canonical_texts(
        candidate_refs, "commit permission candidate_refs", allow_empty=False
    )
    return _root("candidate-set", {"candidate_refs": list(canonical)})


def commit_gate_claims_root_v2(claim_roots: tuple[str, ...]) -> str:
    canonical = _canonical_roots(
        claim_roots, "commit permission claim_roots", allow_empty=True
    )
    return _root("claims", {"claim_roots": list(canonical)})


def commit_stop_reasons_root_v2(reason_codes: tuple[str, ...]) -> str:
    canonical = _canonical_texts(
        reason_codes, "commit stop reason_codes", allow_empty=True
    )
    return _root("stop-reasons", {"reason_codes": list(canonical)})


__all__: tuple[str, ...] = ()
