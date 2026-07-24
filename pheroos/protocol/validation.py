from __future__ import annotations

from pheroos.protocol.authority_manifest_v2 import (
    ScopedCapabilityManifestV2,
    ScopedProtocolManifestV2,
    scoped_capability_manifest_v2_from_dict,
)
from pheroos.protocol._validation_commit_constants import (
    CERTIFICATE_MODE_BY_ASSURANCE as CERTIFICATE_MODE_BY_ASSURANCE,
    COMMIT_ASSURANCE_ORDER as COMMIT_ASSURANCE_ORDER,
    COMMIT_CRITICAL_EXTENSION_PREFIXES as COMMIT_CRITICAL_EXTENSION_PREFIXES,
    NON_PUBLISHABLE_TERMINAL_OUTCOMES as NON_PUBLISHABLE_TERMINAL_OUTCOMES,
)
from pheroos.protocol._validation_commit_finality_rules import (
    validate_certificate_policy as _validate_certificate_policy,
    validate_distributed_commit_policy as _validate_distributed_commit_policy,
    validate_terminal_outcome_policy as _validate_terminal_outcome_policy,
)
from pheroos.protocol._validation_commit_primitives import (
    authority_integer as _authority_integer,
    authority_integer_in_range as _authority_integer_in_range,
)
from pheroos.protocol._validation_commit_risk_rules import (
    validate_risk_bands as _validate_risk_bands,
)
from pheroos.protocol._validation_commit_rules import (
    validate_collective_commit_policy as _validate_collective_commit_policy,
    validate_commit_extensions as _validate_commit_extensions,
    validate_commit_window_policy as _validate_commit_window_policy,
    validate_evidence_qualification_policy as _validate_evidence_qualification_policy,
    validate_support_lease_policy as _validate_support_lease_policy,
)
from pheroos.protocol._validation_manifest_rules import (
    validate_capability_manifest_v1_rules,
)
from pheroos.protocol._validation_primitives import (
    ALLOWED_POLICY_ADJUSTMENT_FIELDS as ALLOWED_POLICY_ADJUSTMENT_FIELDS,
    MAX_LAYER_WEIGHT as MAX_LAYER_WEIGHT,
    POLICY_ADJUSTMENT_ENUM_FIELDS as POLICY_ADJUSTMENT_ENUM_FIELDS,
    POLICY_ADJUSTMENT_NUMERIC_ABSOLUTE_BOUNDS as POLICY_ADJUSTMENT_NUMERIC_ABSOLUTE_BOUNDS,
    SAFETY_CRITICAL_POLICY_ADJUSTMENT_FIELDS as SAFETY_CRITICAL_POLICY_ADJUSTMENT_FIELDS,
    canonical_nonblank_text as _canonical_nonblank_text,
    canonical_string_set as _canonical_string_set,
    collective_kind_weight as _collective_kind_weight,
    duplicate_values as _duplicate_values,
    finite_in_range as _finite_in_range,
    finite_non_negative as _finite_non_negative,
    finite_number as _finite_number,
    non_negative_integer as _non_negative_integer,
    normalized_bounds as _normalized_bounds,
    positive_integer as _positive_integer,
    valid_absolute_bounds as _valid_absolute_bounds,
    valid_non_negative_bounds as _valid_non_negative_bounds,
    valid_policy_adjustment_bound as _valid_policy_adjustment_bound,
    validation_error,
)
from pheroos.protocol.models import (
    CapabilityManifest,
    CollectiveDecisionPolicy,
    ProtocolManifest,
    OutputPolicy,
    ValidationDiagnostic,
)
from pheroos.protocol.commit_models import CollectiveCommitPolicy


def validate_capability_manifest(
    manifest: CapabilityManifest | ScopedCapabilityManifestV2,
) -> list[ValidationDiagnostic]:
    """Validate a canonical capability through its exact Protocol ABI owner.

    The legacy branch intentionally remains the original validator so its
    diagnostics and ordering stay stable. Scoped v2 declarations use their
    closed canonical constructor instead of being projected onto legacy output
    policy fields.
    """

    if type(manifest) is ScopedCapabilityManifestV2:
        return _validate_scoped_capability_manifest_v2(manifest)
    if isinstance(manifest, CapabilityManifest):
        return _validate_capability_manifest_v1(manifest)
    return [
        error(
            "capability_manifest_type_unsupported",
            "capability manifest must use a canonical supported Protocol ABI type",
            "$",
        )
    ]


def _validate_scoped_capability_manifest_v2(
    manifest: ScopedCapabilityManifestV2,
) -> list[ValidationDiagnostic]:
    try:
        payload = manifest.to_dict()
        reconstructed = scoped_capability_manifest_v2_from_dict(payload)
        if reconstructed != manifest or reconstructed.root() != manifest.root():
            raise ValueError("scoped capability does not round-trip exactly")
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return [
            error(
                "scoped_capability_manifest_invalid",
                f"scoped capability manifest is not canonical: {exc}",
                "$",
            )
        ]
    return _scoped_protocol_semantic_diagnostics(reconstructed.protocol)


def _scoped_protocol_semantic_diagnostics(
    protocol: ScopedProtocolManifestV2,
) -> list[ValidationDiagnostic]:
    """Apply the complete shared policy semantics to scoped v2.

    Scoped v2 deliberately replaces the legacy Boolean output policy with an
    action declaration.  All other protocol declarations retain the same
    semantic invariants, so a safe projection lets one validator remain the
    owner of collective, commit, recovery, evidence, and trace rules.  The
    projection uses a fixed supported protocol selector and the strict legacy
    output gates; neither value is accepted from the scoped caller.
    """

    projected_protocol = ProtocolManifest(
        protocol_version="pheroos.protocol.v1",
        id=protocol.id,
        targets=list(protocol.targets),
        candidates=list(protocol.candidates),
        quorum_policy=protocol.quorum_policy,
        recovery_protocols=list(protocol.recovery_protocols),
        output_policy=OutputPolicy(),
        trace_policy=protocol.trace_policy,
        evidence_policy=protocol.evidence_policy,
        signals=list(protocol.signals),
        collective_decision_policy=protocol.collective_decision_policy,
        collective_commit_policy=protocol.collective_commit_policy,
        extensions=dict(protocol.extensions),
    )
    projection = CapabilityManifest(
        id="scoped-v2-semantic-validation",
        name="Scoped v2 semantic validation",
        version="2",
        protocol=projected_protocol,
    )
    return _validate_capability_manifest_v1(projection)


def _validate_capability_manifest_v1(
    manifest: CapabilityManifest,
) -> list[ValidationDiagnostic]:
    return validate_capability_manifest_v1_rules(
        manifest,
        validate_collective_commit_policy,
    )


def validate_collective_commit_policy(
    protocol: ProtocolManifest,
) -> list[ValidationDiagnostic]:
    return _validate_collective_commit_policy(protocol)


def validate_commit_extensions(
    extensions: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    """Keep optional metadata open without accepting unknown critical semantics."""

    return _validate_commit_extensions(extensions, path=path)


def validate_evidence_qualification_policy(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    return _validate_evidence_qualification_policy(policy, path=path)


def validate_support_lease_policy(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    return _validate_support_lease_policy(policy, path=path)


def validate_commit_window_policy(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    return _validate_commit_window_policy(policy, path=path)


def validate_terminal_outcome_policy(
    policy: object,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    return _validate_terminal_outcome_policy(
        policy,
        assurance=assurance,
        path=path,
    )


def validate_certificate_policy(
    policy: object,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    return _validate_certificate_policy(
        policy,
        assurance=assurance,
        path=path,
    )


def validate_distributed_commit_policy(
    policy: object,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    return _validate_distributed_commit_policy(
        policy,
        assurance=assurance,
        path=path,
    )


def validate_risk_bands(
    policy: CollectiveCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    return _validate_risk_bands(policy, path=path)


def authority_integer(value: object) -> bool:
    return _authority_integer(value)


def authority_integer_in_range(value: object, minimum: int, maximum: int) -> bool:
    return _authority_integer_in_range(value, minimum, maximum)


def canonical_nonblank_text(value: object) -> bool:
    return _canonical_nonblank_text(value)


def canonical_string_set(value: object, *, require_nonempty: bool = False) -> bool:
    return _canonical_string_set(value, require_nonempty=require_nonempty)


def validate_ok(
    manifest: CapabilityManifest | ScopedCapabilityManifestV2,
) -> bool:
    return not any(
        item.level == "error" for item in validate_capability_manifest(manifest)
    )


def error(code: str, message: str, path: str) -> ValidationDiagnostic:
    return validation_error(code, message, path)


def duplicate_values(values: object) -> list[str]:
    return _duplicate_values(values)


def collective_kind_weight(policy: CollectiveDecisionPolicy, kind: str) -> float:
    return _collective_kind_weight(policy, kind)


def valid_policy_adjustment_bound(
    field_name: object,
    bounds: object,
    policy: object,
) -> bool:
    return _valid_policy_adjustment_bound(field_name, bounds, policy)


def normalized_bounds(bounds: object) -> tuple[float, float]:
    return _normalized_bounds(bounds)


def valid_absolute_bounds(
    bounds: object, absolute_minimum: float, absolute_maximum: float
) -> bool:
    return _valid_absolute_bounds(bounds, absolute_minimum, absolute_maximum)


def valid_non_negative_bounds(lower: object, upper: object) -> bool:
    return _valid_non_negative_bounds(lower, upper)


def finite_number(value: object) -> bool:
    return _finite_number(value)


def finite_non_negative(value: object) -> bool:
    return _finite_non_negative(value)


def finite_in_range(
    value: object,
    minimum: float,
    maximum: float,
    *,
    lower_inclusive: bool = True,
) -> bool:
    return _finite_in_range(
        value,
        minimum,
        maximum,
        lower_inclusive=lower_inclusive,
    )


def positive_integer(value: object) -> bool:
    return _positive_integer(value)


def non_negative_integer(value: object) -> bool:
    return _non_negative_integer(value)
