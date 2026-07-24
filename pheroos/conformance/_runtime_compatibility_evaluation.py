"""Exact, downgrade-free evaluation for runtime compatibility v1."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from pheroos.conformance._runtime_compatibility_codec import (
    DIGEST_PATTERN,
    RUNTIME_COMPATIBILITY_REPORT_VERSION_V1,
    RuntimeCompatibilityErrorV1,
    text_value,
)
from pheroos.conformance._runtime_compatibility_contracts import (
    RuntimeCompatibilityClaimV1,
    RuntimeCompatibilityComponentClaimV1,
    RuntimeCompatibilityManifestV1,
    RuntimeCompatibilityRequirementV1,
    selection,
)


class RuntimeCompatibilityDiagnosticCodeV1(StrEnum):
    MISSING_COMPONENT = "missing_component"
    VERSION_MISMATCH = "version_mismatch"
    UNKNOWN_CRITICAL_COMPONENT = "unknown_critical_component"
    EXTRA_NONCRITICAL_COMPONENT = "extra_noncritical_component"
    UNKNOWN_OPTIONAL_PROFILE = "unknown_optional_profile"
    UNKNOWN_OPTIONAL_CAPABILITY = "unknown_optional_capability"


@dataclass(frozen=True, slots=True)
class RuntimeCompatibilityDiagnosticV1:
    code: RuntimeCompatibilityDiagnosticCodeV1
    subject: str
    critical: bool
    expected_version: str = ""
    observed_version: str = ""

    def __post_init__(self) -> None:
        try:
            code = RuntimeCompatibilityDiagnosticCodeV1(self.code)
        except (TypeError, ValueError) as exc:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility diagnostic code is unsupported"
            ) from exc
        object.__setattr__(self, "code", code)
        text_value(self.subject, label="runtime compatibility diagnostic subject")
        if type(self.critical) is not bool:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility diagnostic critical flag must be boolean"
            )
        for value, label in (
            (self.expected_version, "expected version"),
            (self.observed_version, "observed version"),
        ):
            if value:
                text_value(value, label=label)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "subject": self.subject,
            "critical": self.critical,
            "expected_version": self.expected_version,
            "observed_version": self.observed_version,
        }


class RuntimeCompatibilityStatusV1(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True, slots=True)
class RuntimeCompatibilityReportV1:
    manifest_root: str
    claim_root: str
    diagnostics: tuple[RuntimeCompatibilityDiagnosticV1, ...] = field(
        default_factory=tuple
    )
    selected_optional_profiles: tuple[str, ...] = ()
    selected_optional_capabilities: tuple[str, ...] = ()
    report_version: str = RUNTIME_COMPATIBILITY_REPORT_VERSION_V1

    def __post_init__(self) -> None:
        if self.report_version != RUNTIME_COMPATIBILITY_REPORT_VERSION_V1:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility report version is unsupported"
            )
        for value, label in (
            (self.manifest_root, "runtime compatibility manifest root"),
            (self.claim_root, "runtime compatibility claim root"),
        ):
            if type(value) is not str or not DIGEST_PATTERN.fullmatch(value):
                raise RuntimeCompatibilityErrorV1(f"{label} is invalid")
        diagnostics = tuple(self.diagnostics)
        if any(
            type(item) is not RuntimeCompatibilityDiagnosticV1 for item in diagnostics
        ):
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility report diagnostics are invalid"
            )
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(
            self,
            "selected_optional_profiles",
            selection(
                self.selected_optional_profiles, label="selected optional profile"
            ),
        )
        object.__setattr__(
            self,
            "selected_optional_capabilities",
            selection(
                self.selected_optional_capabilities,
                label="selected optional capability",
            ),
        )

    @property
    def ok(self) -> bool:
        return not any(item.critical for item in self.diagnostics)

    @property
    def status(self) -> RuntimeCompatibilityStatusV1:
        if self.ok:
            return RuntimeCompatibilityStatusV1.COMPATIBLE
        return RuntimeCompatibilityStatusV1.INCOMPATIBLE

    def to_dict(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "manifest_root": self.manifest_root,
            "claim_root": self.claim_root,
            "status": self.status.value,
            "ok": self.ok,
            "selected_optional_profiles": list(self.selected_optional_profiles),
            "selected_optional_capabilities": list(self.selected_optional_capabilities),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def create_runtime_compatibility_claim_v1(
    component_versions: Mapping[str, str],
    *,
    required_optional_profiles: Iterable[str] = (),
    required_optional_capabilities: Iterable[str] = (),
    critical_components: Iterable[str] = (),
) -> RuntimeCompatibilityClaimV1:
    """Create a deterministic claim; optional requirements stay explicit."""

    if not isinstance(component_versions, Mapping):
        raise RuntimeCompatibilityErrorV1(
            "runtime compatibility component versions must be a mapping"
        )
    critical = frozenset(critical_components)
    for component_id in critical:
        text_value(component_id, label="critical runtime component id")
    if not critical.issubset(component_versions):
        raise RuntimeCompatibilityErrorV1(
            "critical runtime component ids must be present in the claim"
        )
    components = tuple(
        RuntimeCompatibilityComponentClaimV1(
            component_id=component_id,
            version_id=version_id,
            critical=component_id in critical,
        )
        for component_id, version_id in sorted(component_versions.items())
    )
    return RuntimeCompatibilityClaimV1(
        components=components,
        required_optional_profiles=tuple(sorted(required_optional_profiles)),
        required_optional_capabilities=tuple(sorted(required_optional_capabilities)),
    )


def _missing_or_mismatch(
    requirement: RuntimeCompatibilityRequirementV1,
    claims: Mapping[str, RuntimeCompatibilityComponentClaimV1],
) -> RuntimeCompatibilityDiagnosticV1 | None:
    observed = claims.get(requirement.component_id)
    if observed is None:
        return RuntimeCompatibilityDiagnosticV1(
            code=RuntimeCompatibilityDiagnosticCodeV1.MISSING_COMPONENT,
            subject=requirement.component_id,
            critical=True,
            expected_version=requirement.version_id,
        )
    if observed.version_id != requirement.version_id:
        return RuntimeCompatibilityDiagnosticV1(
            code=RuntimeCompatibilityDiagnosticCodeV1.VERSION_MISMATCH,
            subject=requirement.component_id,
            critical=True,
            expected_version=requirement.version_id,
            observed_version=observed.version_id,
        )
    return None


def _selected_requirements(
    manifest: RuntimeCompatibilityManifestV1,
    claim: RuntimeCompatibilityClaimV1,
) -> tuple[
    list[RuntimeCompatibilityRequirementV1],
    list[RuntimeCompatibilityDiagnosticV1],
]:
    requirements = list(manifest.required_profile.requirements)
    diagnostics: list[RuntimeCompatibilityDiagnosticV1] = []
    profiles = {item.profile_id: item for item in manifest.optional_profiles}
    capabilities = {item.capability_id: item for item in manifest.optional_capabilities}
    for profile_id in claim.required_optional_profiles:
        selected = profiles.get(profile_id)
        if selected is None:
            diagnostics.append(
                RuntimeCompatibilityDiagnosticV1(
                    RuntimeCompatibilityDiagnosticCodeV1.UNKNOWN_OPTIONAL_PROFILE,
                    profile_id,
                    True,
                )
            )
            continue
        requirements.extend(selected.requirements)
    for capability_id in claim.required_optional_capabilities:
        selected_capability = capabilities.get(capability_id)
        if selected_capability is None:
            diagnostics.append(
                RuntimeCompatibilityDiagnosticV1(
                    RuntimeCompatibilityDiagnosticCodeV1.UNKNOWN_OPTIONAL_CAPABILITY,
                    capability_id,
                    True,
                )
            )
            continue
        requirements.extend(selected_capability.requirements)
    return requirements, diagnostics


def _known_component_ids(manifest: RuntimeCompatibilityManifestV1) -> set[str]:
    result = {item.component_id for item in manifest.required_profile.requirements}
    for profile in manifest.optional_profiles:
        result.update(item.component_id for item in profile.requirements)
    for capability in manifest.optional_capabilities:
        result.update(item.component_id for item in capability.requirements)
    return result


def _extra_component_diagnostics(
    manifest: RuntimeCompatibilityManifestV1,
    claim: RuntimeCompatibilityClaimV1,
) -> list[RuntimeCompatibilityDiagnosticV1]:
    known = _known_component_ids(manifest)
    diagnostics: list[RuntimeCompatibilityDiagnosticV1] = []
    for component in claim.components:
        if component.component_id in known:
            continue
        code = (
            RuntimeCompatibilityDiagnosticCodeV1.UNKNOWN_CRITICAL_COMPONENT
            if component.critical
            else RuntimeCompatibilityDiagnosticCodeV1.EXTRA_NONCRITICAL_COMPONENT
        )
        diagnostics.append(
            RuntimeCompatibilityDiagnosticV1(
                code,
                component.component_id,
                component.critical,
                observed_version=component.version_id,
            )
        )
    return diagnostics


def evaluate_runtime_compatibility_v1(
    manifest: RuntimeCompatibilityManifestV1,
    claim: RuntimeCompatibilityClaimV1,
) -> RuntimeCompatibilityReportV1:
    """Return a typed exact-match report without semver or downgrade guesses."""

    if type(manifest) is not RuntimeCompatibilityManifestV1:
        raise TypeError("manifest must be RuntimeCompatibilityManifestV1")
    if type(claim) is not RuntimeCompatibilityClaimV1:
        raise TypeError("claim must be RuntimeCompatibilityClaimV1")
    claims = {item.component_id: item for item in claim.components}
    requirements, diagnostics = _selected_requirements(manifest, claim)
    for requirement in sorted(requirements, key=lambda item: item.component_id):
        diagnostic = _missing_or_mismatch(requirement, claims)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    diagnostics.extend(_extra_component_diagnostics(manifest, claim))
    return RuntimeCompatibilityReportV1(
        manifest_root=manifest.manifest_root,
        claim_root=claim.claim_root,
        diagnostics=tuple(diagnostics),
        selected_optional_profiles=claim.required_optional_profiles,
        selected_optional_capabilities=claim.required_optional_capabilities,
    )


__all__ = [
    "RuntimeCompatibilityDiagnosticCodeV1",
    "RuntimeCompatibilityDiagnosticV1",
    "RuntimeCompatibilityReportV1",
    "RuntimeCompatibilityStatusV1",
    "create_runtime_compatibility_claim_v1",
    "evaluate_runtime_compatibility_v1",
]
