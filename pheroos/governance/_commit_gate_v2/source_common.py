"""Shared exact-manifest and source-proof support for Commit Gate v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, SupportsIndex

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._commit_gate_v2.common import (
    _require_count,
    _require_text,
    _root,
)
from pheroos.governance._commit_gate_v2.dependency_contracts import (
    CommitGateDependenciesV2,
)
from pheroos.governance._support_v2.durable_context import durable_support_context_v2


@dataclass(frozen=True, slots=True)
class _ValidatedGateContextV2:
    manifest: ScopedProtocolManifestV2
    manifest_root: str
    commit_policy_root: str
    profile: str
    assurance: CommitAssurance
    protocol_ref: str
    candidate_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _GateSourceMaterialV2:
    kind: str
    request_root: str
    evaluation_context_root: str
    dependency_root: str
    source_context_root: str


class _VerifiedGateSourceBaseV2:
    __slots__ = ("_manifest", "_material", "_preconditions", "_request")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __reduce__(self) -> NoReturn:
        raise TypeError(f"{type(self).__name__} is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError(f"{type(self).__name__} is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError(f"{type(self).__name__} is not portable")

    @property
    def context_root(self) -> str:
        material = object.__getattribute__(self, "_material")
        if type(material) is not _GateSourceMaterialV2:
            raise TypeError("commit gate source material is invalid")
        return material.source_context_root


def _validated_gate_context_v2(
    *,
    domain_root: str,
    scope_ref: str,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    run_ref: str,
    target_ref: str,
    observed_epoch: int,
    request_ref: str,
    current_step: int,
    mutation_issuer_ref: str,
) -> _ValidatedGateContextV2:
    _require_root(domain_root, "commit gate source domain_root")
    for label, value in (
        ("scope_ref", scope_ref),
        ("profile", profile),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
        ("request_ref", request_ref),
        ("mutation_issuer_ref", mutation_issuer_ref),
    ):
        _require_text(value, f"commit gate source {label}")
    _require_count(observed_epoch, "commit gate source observed_epoch")
    _require_count(current_step, "commit gate source current_step")
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("Commit Gate v2 requires exact ScopedProtocolManifestV2")
    detached = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    policy = detached.collective_commit_policy
    if policy is None:
        raise ValueError("Commit Gate v2 manifest has no collective commit policy")
    try:
        assurance = CommitAssurance(policy.assurance)
    except (TypeError, ValueError) as exc:
        raise ValueError("Commit Gate v2 assurance is unsupported") from exc
    context = durable_support_context_v2(
        detached,
        profile=profile,
        assurance=assurance,
        target_ref=target_ref,
    )
    candidates = tuple(
        sorted(
            (item.id for item in detached.candidates if item.target == target_ref),
            key=lambda item: item.encode("utf-8"),
        )
    )
    if not candidates:
        raise ValueError("Commit Gate v2 target has no declared candidates")
    return _ValidatedGateContextV2(
        manifest=detached,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        profile=profile,
        assurance=assurance,
        protocol_ref=context.protocol_ref,
        candidate_refs=candidates,
    )


def _source_context_root_v2(
    *,
    kind: str,
    request_root: str,
    evaluation_context_root: str,
    dependency_root: str,
) -> str:
    for label, value in (
        ("request_root", request_root),
        ("evaluation_context_root", evaluation_context_root),
        ("dependency_root", dependency_root),
    ):
        _require_root(value, f"commit gate source {label}")
    return _root(
        "source-context",
        {
            "kind": kind,
            "request_root": request_root,
            "evaluation_context_root": evaluation_context_root,
            "dependency_root": dependency_root,
        },
    )


def _dependency_preconditions_v2(
    dependencies: CommitGateDependenciesV2,
) -> tuple[GovernanceReadPreconditionV2, ...]:
    if type(dependencies) is not CommitGateDependenciesV2:
        raise TypeError("commit gate source dependencies are invalid")
    values = tuple(
        GovernanceReadPreconditionV2(
            stream_ref=getattr(dependencies, f"{name}_stream_ref"),
            expected_revision=getattr(dependencies, f"{name}_revision"),
            expected_root=getattr(dependencies, f"{name}_head_root"),
        )
        for name in ("replay", "risk", "verification", "membership", "support")
    )
    return tuple(sorted(values, key=lambda item: item.stream_ref.encode("utf-8")))


def _issue_gate_source_v2(
    source_type: type[_VerifiedGateSourceBaseV2],
    *,
    kind: str,
    request: object,
    request_root: str,
    evaluation_context_root: str,
    dependencies: CommitGateDependenciesV2,
    manifest: ScopedProtocolManifestV2,
    preconditions: tuple[GovernanceReadPreconditionV2, ...],
) -> _VerifiedGateSourceBaseV2:
    expected_preconditions = _dependency_preconditions_v2(dependencies)
    if preconditions != expected_preconditions:
        raise ValueError("commit gate source preconditions are mismatched")
    material = _GateSourceMaterialV2(
        kind=kind,
        request_root=request_root,
        evaluation_context_root=evaluation_context_root,
        dependency_root=dependencies.dependency_root,
        source_context_root=_source_context_root_v2(
            kind=kind,
            request_root=request_root,
            evaluation_context_root=evaluation_context_root,
            dependency_root=dependencies.dependency_root,
        ),
    )
    source = object.__new__(source_type)
    object.__setattr__(source, "_request", request)
    object.__setattr__(
        source, "_manifest", ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    )
    object.__setattr__(source, "_material", material)
    object.__setattr__(source, "_preconditions", tuple(preconditions))
    return source


def _verified_gate_source_fields_v2(
    source: object,
    *,
    expected_type: type[_VerifiedGateSourceBaseV2],
    expected_kind: str,
    expected_request_type: type[object],
) -> tuple[
    object,
    ScopedProtocolManifestV2,
    _GateSourceMaterialV2,
    tuple[GovernanceReadPreconditionV2, ...],
]:
    if type(source) is not expected_type:
        raise TypeError("commit gate source has the wrong exact type")
    try:
        request: object = object.__getattribute__(source, "_request")
        manifest: object = object.__getattribute__(source, "_manifest")
        material: object = object.__getattribute__(source, "_material")
        preconditions: object = object.__getattribute__(source, "_preconditions")
    except AttributeError as exc:
        raise TypeError("commit gate source is incomplete") from exc
    if (
        type(request) is not expected_request_type
        or type(manifest) is not ScopedProtocolManifestV2
        or type(material) is not _GateSourceMaterialV2
        or type(preconditions) is not tuple
        or any(type(item) is not GovernanceReadPreconditionV2 for item in preconditions)
        or material.kind != expected_kind
    ):
        raise TypeError("commit gate source material is invalid")
    detached_manifest = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    normalized_preconditions = tuple(
        GovernanceReadPreconditionV2.from_dict(item.to_dict()) for item in preconditions
    )
    return request, detached_manifest, material, normalized_preconditions


__all__: tuple[str, ...] = ()
