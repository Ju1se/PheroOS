"""Opaque proof storage and replay verification for Commit Decision v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2

from pheroos.governance._commit_decision_v2.assessment_records import (
    CommitAssessmentV2,
)
from pheroos.governance._commit_decision_v2.common import _require_root, _root
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    canonical_commit_decision_dependencies_v2,
    dependency_by_role_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionDependencyRoleV2,
)
from pheroos.governance._commit_decision_v2.gate_status import (
    CommitDecisionGateStatusV2,
)
from pheroos.governance._commit_decision_v2.reducer import reduce_commit_decision_v2
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.seal_inclusion import (
    CommitDecisionSealInclusionV2,
)
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2
from pheroos.governance._commit_finality_v2 import CommitFinalityProjectionV2


_SOURCE_TOKEN_V2 = object()


@dataclass(frozen=True, slots=True)
class _CommitDecisionSourceMaterialV2:
    request: CommitDecisionRequestV2
    manifest: ScopedProtocolManifestV2
    profile: str
    dependencies: tuple[CommitDecisionDependencyV2, ...]
    parent: CommitDecisionSnapshotV2 | None
    assessment: CommitAssessmentV2 | None
    required_stability_steps: int
    finality: CommitFinalityProjectionV2 | None
    finality_input_root: str
    seal_inclusion: CommitDecisionSealInclusionV2 | None
    gate_status: CommitDecisionGateStatusV2 | None
    source_context_root: str
    snapshot: CommitDecisionSnapshotV2


@final
class VerifiedCommitDecisionSourceV2:
    """Opaque derivation bundle; its token alone grants no write authority.

    Commit still re-derives the replacement, reloads every declared Store
    head, and atomically binds dependency, grant, and lifecycle preconditions.
    """

    __slots__ = (
        "_assessment",
        "_dependencies",
        "_finality",
        "_finality_input_root",
        "_gate_status",
        "_manifest",
        "_parent",
        "_profile",
        "_request",
        "_required_stability_steps",
        "_seal_inclusion",
        "_snapshot",
        "_source_context_root",
        "_token",
    )

    def __new__(
        cls,
        *_args: object,
        **_kwargs: object,
    ) -> VerifiedCommitDecisionSourceV2:
        raise TypeError("VerifiedCommitDecisionSourceV2 cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitDecisionSourceV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedCommitDecisionSourceV2 is immutable")

    def __copy__(self) -> VerifiedCommitDecisionSourceV2:
        _verified_source_material_v2(self)
        return self

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> VerifiedCommitDecisionSourceV2:
        _verified_source_material_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedCommitDecisionSourceV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedCommitDecisionSourceV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedCommitDecisionSourceV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedCommitDecisionSourceV2 redacted>"


def verify_commit_decision_request_source_v2(
    request: CommitDecisionRequestV2,
    *,
    source: object,
    committed_parent_snapshot: CommitDecisionSnapshotV2 | None,
) -> tuple[
    CommitDecisionSnapshotV2,
    tuple[CommitDecisionDependencyV2, ...],
    str,
]:
    """Rebuild the replacement and reject any mutable source substitution."""

    if type(request) is not CommitDecisionRequestV2:
        raise TypeError("commit decision source verification requires exact request")
    material = _verified_source_material_v2(source)
    if material.request.to_dict() != request.to_dict():
        raise ValueError("commit decision source request is mismatched")
    if (material.parent is None) != (committed_parent_snapshot is None):
        raise ValueError("commit decision source parent presence is mismatched")
    if material.parent is not None and committed_parent_snapshot is not None:
        if material.parent.to_dict() != committed_parent_snapshot.to_dict():
            raise ValueError("commit decision source committed parent is mismatched")
    expected_source = _source_context_root_v2(
        request=request,
        manifest=material.manifest,
        dependencies=material.dependencies,
        parent=committed_parent_snapshot,
        assessment=material.assessment,
        finality=material.finality,
        finality_input_root=material.finality_input_root,
        seal_inclusion=material.seal_inclusion,
        gate_status=material.gate_status,
    )
    if expected_source != material.source_context_root:
        raise ValueError("commit decision source context is mismatched")
    rebuilt = reduce_commit_decision_v2(
        request,
        manifest=material.manifest,
        profile=material.profile,
        dependencies=material.dependencies,
        source_context_root=material.source_context_root,
        parent=committed_parent_snapshot,
        assessment=material.assessment,
        required_stability_steps=material.required_stability_steps,
        verified_finality=material.finality,
        verified_seal_inclusion=material.seal_inclusion,
        current_gate_status=material.gate_status,
    )
    if rebuilt.to_dict() != material.snapshot.to_dict():
        raise ValueError("commit decision source replacement is mismatched")
    return rebuilt, material.dependencies, material.source_context_root


def _issue_source_v2(
    *,
    request: CommitDecisionRequestV2,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    dependencies: Sequence[CommitDecisionDependencyV2],
    parent: CommitDecisionSnapshotV2 | None,
    assessment: CommitAssessmentV2 | None,
    required_stability_steps: int,
    finality: CommitFinalityProjectionV2 | None,
    finality_input_root: str,
    seal_inclusion: CommitDecisionSealInclusionV2 | None,
    gate_status: CommitDecisionGateStatusV2 | None,
    source_context_root: str,
    snapshot: CommitDecisionSnapshotV2,
) -> VerifiedCommitDecisionSourceV2:
    source = object.__new__(VerifiedCommitDecisionSourceV2)
    object.__setattr__(source, "_token", _SOURCE_TOKEN_V2)
    object.__setattr__(
        source,
        "_request",
        CommitDecisionRequestV2.from_dict(request.to_dict()),
    )
    object.__setattr__(
        source,
        "_manifest",
        ScopedProtocolManifestV2.from_dict(manifest.to_dict()),
    )
    object.__setattr__(source, "_profile", profile)
    object.__setattr__(
        source,
        "_dependencies",
        canonical_commit_decision_dependencies_v2(dependencies),
    )
    object.__setattr__(
        source,
        "_parent",
        None
        if parent is None
        else CommitDecisionSnapshotV2.from_dict(parent.to_dict()),
    )
    object.__setattr__(
        source,
        "_assessment",
        None
        if assessment is None
        else CommitAssessmentV2.from_dict(assessment.to_dict()),
    )
    object.__setattr__(
        source,
        "_required_stability_steps",
        required_stability_steps,
    )
    object.__setattr__(
        source,
        "_finality",
        None
        if finality is None
        else CommitFinalityProjectionV2.from_dict(finality.to_dict()),
    )
    object.__setattr__(source, "_finality_input_root", finality_input_root)
    object.__setattr__(
        source,
        "_seal_inclusion",
        None
        if seal_inclusion is None
        else CommitDecisionSealInclusionV2.from_dict(seal_inclusion.to_dict()),
    )
    object.__setattr__(
        source,
        "_gate_status",
        None
        if gate_status is None
        else CommitDecisionGateStatusV2.from_dict(gate_status.to_dict()),
    )
    object.__setattr__(source, "_source_context_root", source_context_root)
    object.__setattr__(
        source,
        "_snapshot",
        CommitDecisionSnapshotV2.from_dict(snapshot.to_dict()),
    )
    return source


def _verified_source_material_v2(
    source: object,
) -> _CommitDecisionSourceMaterialV2:
    if type(source) is not VerifiedCommitDecisionSourceV2:
        raise TypeError("commit decision source has the wrong exact type")
    try:
        token = object.__getattribute__(source, "_token")
    except AttributeError as exc:
        raise TypeError("commit decision source is incomplete") from exc
    if token is not _SOURCE_TOKEN_V2:
        raise TypeError("commit decision source authority token is invalid")
    names = (
        "_request",
        "_manifest",
        "_profile",
        "_dependencies",
        "_parent",
        "_assessment",
        "_required_stability_steps",
        "_finality",
        "_finality_input_root",
        "_seal_inclusion",
        "_gate_status",
        "_source_context_root",
        "_snapshot",
    )
    try:
        values = tuple(object.__getattribute__(source, name) for name in names)
    except AttributeError as exc:
        raise TypeError("commit decision source is incomplete") from exc
    return _validated_source_material_v2(values)


def _validated_source_material_v2(
    values: tuple[object, ...],
) -> _CommitDecisionSourceMaterialV2:
    (
        request,
        manifest,
        profile,
        dependencies,
        parent,
        assessment,
        required,
        finality,
        finality_input_root,
        seal_inclusion,
        gate_status,
        root,
        snapshot,
    ) = values
    if (
        type(request) is not CommitDecisionRequestV2
        or type(manifest) is not ScopedProtocolManifestV2
        or type(profile) is not str
    ):
        raise TypeError("commit decision source context is invalid")
    canonical_commit_decision_dependencies_v2(
        cast(Sequence[CommitDecisionDependencyV2], dependencies)
    )
    if parent is not None and type(parent) is not CommitDecisionSnapshotV2:
        raise TypeError("commit decision source parent is invalid")
    if assessment is not None and type(assessment) is not CommitAssessmentV2:
        raise TypeError("commit decision source assessment is invalid")
    if type(required) is not int or required < 1:
        raise TypeError("commit decision source stability threshold is invalid")
    if finality is not None and type(finality) is not CommitFinalityProjectionV2:
        raise TypeError("commit decision source finality is invalid")
    _require_root(
        finality_input_root,
        "commit decision finality input root",
        allow_empty=True,
    )
    if (finality is None) != (finality_input_root == ""):
        raise ValueError("commit decision finality input binding is inconsistent")
    if (
        seal_inclusion is not None
        and type(seal_inclusion) is not CommitDecisionSealInclusionV2
    ):
        raise TypeError("commit decision source seal inclusion is invalid")
    if gate_status is not None and type(gate_status) is not CommitDecisionGateStatusV2:
        raise TypeError("commit decision source gate status is invalid")
    _require_root(root, "commit decision source context root")
    if type(snapshot) is not CommitDecisionSnapshotV2:
        raise TypeError("commit decision source snapshot is invalid")
    return _CommitDecisionSourceMaterialV2(
        request=(request),
        manifest=(manifest),
        profile=(profile),
        dependencies=canonical_commit_decision_dependencies_v2(
            cast(Sequence[CommitDecisionDependencyV2], dependencies)
        ),
        parent=(parent),
        assessment=(assessment),
        required_stability_steps=(required),
        finality=(finality),
        finality_input_root=cast(str, finality_input_root),
        seal_inclusion=(seal_inclusion),
        gate_status=(gate_status),
        source_context_root=cast(str, root),
        snapshot=(snapshot),
    )


def _source_context_root_v2(
    *,
    request: CommitDecisionRequestV2,
    manifest: ScopedProtocolManifestV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    parent: CommitDecisionSnapshotV2 | None,
    assessment: CommitAssessmentV2 | None,
    finality: CommitFinalityProjectionV2 | None,
    finality_input_root: str,
    seal_inclusion: CommitDecisionSealInclusionV2 | None,
    gate_status: CommitDecisionGateStatusV2 | None,
) -> str:
    _require_root(
        finality_input_root,
        "commit decision finality input root",
        allow_empty=True,
    )
    canonical = canonical_commit_decision_dependencies_v2(dependencies)
    return _root(
        "source-context",
        {
            "request_root": request.request_root,
            "manifest_root": manifest.manifest_root,
            "dependency_roots": [item.dependency_root for item in canonical],
            "parent_snapshot_root": "" if parent is None else parent.snapshot_root,
            "assessment_root": "" if assessment is None else assessment.assessment_root,
            "finality_projection_root": ""
            if finality is None
            else finality.projection_root,
            "finality_input_root": finality_input_root,
            "seal_inclusion_root": ""
            if seal_inclusion is None
            else seal_inclusion.projection_root,
            "gate_status_root": "" if gate_status is None else gate_status.status_root,
        },
    )


def _source_parent_dependency_v2(source: object) -> CommitDecisionDependencyV2:
    dependencies = _verified_source_material_v2(source).dependencies
    dependency = dependency_by_role_v2(
        dependencies,
        CommitDecisionDependencyRoleV2.PARENT,
    )
    return CommitDecisionDependencyV2.from_dict(dependency.to_dict())


__all__: tuple[str, ...] = ()
