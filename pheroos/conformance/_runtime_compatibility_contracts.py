"""Closed immutable contracts for runtime compatibility v1 documents."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pheroos.conformance._runtime_compatibility_codec import (
    CLAIM_ROOT_PREFIX,
    MANIFEST_ROOT_PREFIX,
    MAX_OPTIONAL_CAPABILITIES,
    MAX_OPTIONAL_PROFILES,
    MAX_REQUIREMENTS,
    RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1,
    RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1,
    RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1,
    RuntimeCompatibilityErrorV1,
    canonical_bytes,
    document_root,
    load_canonical_json,
    text_value,
)


@dataclass(frozen=True, slots=True)
class RuntimeCompatibilityRequirementV1:
    """One exact component/version requirement."""

    component_id: str
    version_id: str

    def __post_init__(self) -> None:
        text_value(self.component_id, label="compatibility component id")
        text_value(self.version_id, label="compatibility version id")

    def to_dict(self) -> dict[str, str]:
        return {"component_id": self.component_id, "version_id": self.version_id}

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeCompatibilityRequirementV1:
        if type(payload) is not dict or set(payload) != {
            "component_id",
            "version_id",
        }:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility requirement fields are invalid"
            )
        return cls(payload["component_id"], payload["version_id"])


def _requirements(
    values: Iterable[RuntimeCompatibilityRequirementV1], *, label: str
) -> tuple[RuntimeCompatibilityRequirementV1, ...]:
    result = tuple(values)
    if not result or len(result) > MAX_REQUIREMENTS:
        raise RuntimeCompatibilityErrorV1(
            f"{label} must contain 1..{MAX_REQUIREMENTS} requirements"
        )
    if any(type(item) is not RuntimeCompatibilityRequirementV1 for item in result):
        raise RuntimeCompatibilityErrorV1(
            f"{label} must contain exact compatibility requirements"
        )
    identities = tuple(item.component_id for item in result)
    if len(identities) != len(set(identities)):
        raise RuntimeCompatibilityErrorV1(f"{label} contains duplicate components")
    if identities != tuple(sorted(identities)):
        raise RuntimeCompatibilityErrorV1(
            f"{label} requirements must use deterministic component order"
        )
    return result


@dataclass(frozen=True, slots=True)
class RuntimeCompatibilityProfileSpecV1:
    """A required or opt-in conformance profile and its exact dependencies."""

    profile_id: str
    profile_version: str
    requirements: tuple[RuntimeCompatibilityRequirementV1, ...]

    def __post_init__(self) -> None:
        text_value(self.profile_id, label="runtime compatibility profile id")
        text_value(self.profile_version, label="runtime compatibility profile version")
        object.__setattr__(
            self,
            "requirements",
            _requirements(self.requirements, label=f"profile {self.profile_id}"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "requirements": [item.to_dict() for item in self.requirements],
        }

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeCompatibilityProfileSpecV1:
        if type(payload) is not dict or set(payload) != {
            "profile_id",
            "profile_version",
            "requirements",
        }:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility profile fields are invalid"
            )
        raw = payload["requirements"]
        if type(raw) is not list:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility profile requirements must be an array"
            )
        return cls(
            profile_id=payload["profile_id"],
            profile_version=payload["profile_version"],
            requirements=tuple(
                RuntimeCompatibilityRequirementV1.from_dict(item) for item in raw
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeCompatibilityCapabilitySpecV1:
    """An opt-in standalone ABI/TCK capability, not a manifest profile."""

    capability_id: str
    requirements: tuple[RuntimeCompatibilityRequirementV1, ...]

    def __post_init__(self) -> None:
        text_value(self.capability_id, label="runtime compatibility capability id")
        object.__setattr__(
            self,
            "requirements",
            _requirements(self.requirements, label=f"capability {self.capability_id}"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "requirements": [item.to_dict() for item in self.requirements],
        }

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeCompatibilityCapabilitySpecV1:
        if type(payload) is not dict or set(payload) != {
            "capability_id",
            "requirements",
        }:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility capability fields are invalid"
            )
        raw = payload["requirements"]
        if type(raw) is not list:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility capability requirements must be an array"
            )
        return cls(
            capability_id=payload["capability_id"],
            requirements=tuple(
                RuntimeCompatibilityRequirementV1.from_dict(item) for item in raw
            ),
        )


def _unique_sorted_specs(
    values: Sequence[object],
    *,
    item_type: type,
    identity_name: str,
    label: str,
    maximum: int,
) -> tuple[object, ...]:
    result = tuple(values)
    if not result or len(result) > maximum:
        raise RuntimeCompatibilityErrorV1(f"{label} must contain 1..{maximum} entries")
    if any(type(item) is not item_type for item in result):
        raise RuntimeCompatibilityErrorV1(f"{label} contains an invalid entry")
    identities = tuple(getattr(item, identity_name) for item in result)
    if len(identities) != len(set(identities)):
        raise RuntimeCompatibilityErrorV1(f"{label} contains duplicate identities")
    if identities != tuple(sorted(identities)):
        raise RuntimeCompatibilityErrorV1(
            f"{label} must use deterministic identity order"
        )
    return result


@dataclass(frozen=True, slots=True)
class RuntimeCompatibilityManifestV1:
    """Closed manifest for one exact, provider-neutral runtime composition."""

    required_profile: RuntimeCompatibilityProfileSpecV1
    optional_profiles: tuple[RuntimeCompatibilityProfileSpecV1, ...]
    optional_capabilities: tuple[RuntimeCompatibilityCapabilitySpecV1, ...]
    manifest_version: str = RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1
    manifest_root: str = ""

    def __post_init__(self) -> None:
        if self.manifest_version != RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility manifest version is unsupported"
            )
        if type(self.required_profile) is not RuntimeCompatibilityProfileSpecV1:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility required profile is invalid"
            )
        profiles = _unique_sorted_specs(
            self.optional_profiles,
            item_type=RuntimeCompatibilityProfileSpecV1,
            identity_name="profile_id",
            label="runtime compatibility optional profiles",
            maximum=MAX_OPTIONAL_PROFILES,
        )
        capabilities = _unique_sorted_specs(
            self.optional_capabilities,
            item_type=RuntimeCompatibilityCapabilitySpecV1,
            identity_name="capability_id",
            label="runtime compatibility optional capabilities",
            maximum=MAX_OPTIONAL_CAPABILITIES,
        )
        object.__setattr__(self, "optional_profiles", profiles)
        object.__setattr__(self, "optional_capabilities", capabilities)
        self._validate_component_namespace()
        expected = document_root(MANIFEST_ROOT_PREFIX, self._projection())
        if self.manifest_root and self.manifest_root != expected:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility manifest root does not match its content"
            )
        object.__setattr__(self, "manifest_root", expected)
        if len(self.canonical_bytes()) > RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility manifest exceeds the wire size bound"
            )

    def _validate_component_namespace(self) -> None:
        requirements = list(self.required_profile.requirements)
        for profile in self.optional_profiles:
            requirements.extend(profile.requirements)
        for capability in self.optional_capabilities:
            requirements.extend(capability.requirements)
        identities = tuple(item.component_id for item in requirements)
        if len(identities) != len(set(identities)):
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility components must have one declared owner"
            )

    def _projection(self) -> dict[str, object]:
        return {
            "manifest_version": self.manifest_version,
            "required_profile": self.required_profile.to_dict(),
            "optional_profiles": [item.to_dict() for item in self.optional_profiles],
            "optional_capabilities": [
                item.to_dict() for item in self.optional_capabilities
            ],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._projection(), "manifest_root": self.manifest_root}

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    @property
    def artifact_digest(self) -> str:
        return "sha256:" + sha256(self.canonical_bytes()).hexdigest()

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeCompatibilityManifestV1:
        fields = {
            "manifest_version",
            "manifest_root",
            "required_profile",
            "optional_profiles",
            "optional_capabilities",
        }
        if type(payload) is not dict or set(payload) != fields:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility manifest fields are invalid"
            )
        profiles = payload["optional_profiles"]
        capabilities = payload["optional_capabilities"]
        if type(profiles) is not list or type(capabilities) is not list:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility option declarations must be arrays"
            )
        return cls(
            manifest_version=payload["manifest_version"],
            manifest_root=payload["manifest_root"],
            required_profile=RuntimeCompatibilityProfileSpecV1.from_dict(
                payload["required_profile"]
            ),
            optional_profiles=tuple(
                RuntimeCompatibilityProfileSpecV1.from_dict(item) for item in profiles
            ),
            optional_capabilities=tuple(
                RuntimeCompatibilityCapabilitySpecV1.from_dict(item)
                for item in capabilities
            ),
        )

    @classmethod
    def from_wire(cls, data: bytes) -> RuntimeCompatibilityManifestV1:
        payload = load_canonical_json(data, label="runtime compatibility manifest")
        manifest = cls.from_dict(payload)
        if data != manifest.canonical_bytes():
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility manifest wire is not canonical"
            )
        return manifest


@dataclass(frozen=True, slots=True)
class RuntimeCompatibilityComponentClaimV1:
    """A runtime's exact component version claim."""

    component_id: str
    version_id: str
    critical: bool

    def __post_init__(self) -> None:
        text_value(self.component_id, label="runtime component claim id")
        text_value(self.version_id, label="runtime component claim version")
        if type(self.critical) is not bool:
            raise RuntimeCompatibilityErrorV1(
                "runtime component claim critical flag must be boolean"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "version_id": self.version_id,
            "critical": self.critical,
        }

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeCompatibilityComponentClaimV1:
        if type(payload) is not dict or set(payload) != {
            "component_id",
            "version_id",
            "critical",
        }:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility component claim fields are invalid"
            )
        return cls(
            component_id=payload["component_id"],
            version_id=payload["version_id"],
            critical=payload["critical"],
        )


def selection(values: Iterable[str], *, label: str) -> tuple[str, ...]:
    result = tuple(values)
    if len(result) > MAX_OPTIONAL_CAPABILITIES:
        raise RuntimeCompatibilityErrorV1(f"{label} exceeds the selection bound")
    for item in result:
        text_value(item, label=label)
    if len(result) != len(set(result)):
        raise RuntimeCompatibilityErrorV1(f"{label} contains duplicates")
    if result != tuple(sorted(result)):
        raise RuntimeCompatibilityErrorV1(
            f"{label} must use deterministic identity order"
        )
    return result


@dataclass(frozen=True, slots=True)
class RuntimeCompatibilityClaimV1:
    """Portable component offer plus explicitly selected optional requirements."""

    components: tuple[RuntimeCompatibilityComponentClaimV1, ...]
    required_optional_profiles: tuple[str, ...] = ()
    required_optional_capabilities: tuple[str, ...] = ()
    claim_version: str = RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1
    claim_root: str = ""

    def __post_init__(self) -> None:
        if self.claim_version != RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim version is unsupported"
            )
        components = tuple(self.components)
        if not components or len(components) > MAX_REQUIREMENTS:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim must contain bounded components"
            )
        if any(
            type(item) is not RuntimeCompatibilityComponentClaimV1
            for item in components
        ):
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim components are invalid"
            )
        identities = tuple(item.component_id for item in components)
        if len(identities) != len(set(identities)):
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim contains duplicate components"
            )
        if identities != tuple(sorted(identities)):
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim components must be sorted"
            )
        object.__setattr__(self, "components", components)
        object.__setattr__(
            self,
            "required_optional_profiles",
            selection(
                self.required_optional_profiles, label="required optional profile"
            ),
        )
        object.__setattr__(
            self,
            "required_optional_capabilities",
            selection(
                self.required_optional_capabilities,
                label="required optional capability",
            ),
        )
        expected = document_root(CLAIM_ROOT_PREFIX, self._projection())
        if self.claim_root and self.claim_root != expected:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim root does not match its content"
            )
        object.__setattr__(self, "claim_root", expected)
        if len(self.canonical_bytes()) > RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim exceeds the wire size bound"
            )

    def _projection(self) -> dict[str, object]:
        return {
            "claim_version": self.claim_version,
            "components": [item.to_dict() for item in self.components],
            "required_optional_profiles": list(self.required_optional_profiles),
            "required_optional_capabilities": list(self.required_optional_capabilities),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._projection(), "claim_root": self.claim_root}

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    @property
    def artifact_digest(self) -> str:
        return "sha256:" + sha256(self.canonical_bytes()).hexdigest()

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeCompatibilityClaimV1:
        fields = {
            "claim_version",
            "claim_root",
            "components",
            "required_optional_profiles",
            "required_optional_capabilities",
        }
        if type(payload) is not dict or set(payload) != fields:
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim fields are invalid"
            )
        components = payload["components"]
        profiles = payload["required_optional_profiles"]
        capabilities = payload["required_optional_capabilities"]
        if (
            type(components) is not list
            or type(profiles) is not list
            or type(capabilities) is not list
        ):
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim collections must be arrays"
            )
        return cls(
            claim_version=payload["claim_version"],
            claim_root=payload["claim_root"],
            components=tuple(
                RuntimeCompatibilityComponentClaimV1.from_dict(item)
                for item in components
            ),
            required_optional_profiles=tuple(profiles),
            required_optional_capabilities=tuple(capabilities),
        )

    @classmethod
    def from_wire(cls, data: bytes) -> RuntimeCompatibilityClaimV1:
        payload = load_canonical_json(data, label="runtime compatibility claim")
        claim = cls.from_dict(payload)
        if data != claim.canonical_bytes():
            raise RuntimeCompatibilityErrorV1(
                "runtime compatibility claim wire is not canonical"
            )
        return claim


__all__ = [
    "RuntimeCompatibilityCapabilitySpecV1",
    "RuntimeCompatibilityClaimV1",
    "RuntimeCompatibilityComponentClaimV1",
    "RuntimeCompatibilityManifestV1",
    "RuntimeCompatibilityProfileSpecV1",
    "RuntimeCompatibilityRequirementV1",
    "selection",
]
