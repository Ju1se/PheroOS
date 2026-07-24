"""Immutable Commit Wire v1 schema and semantic contracts.

This package is private implementation.  The stable public owner remains
``pheroos.governance.schema``.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, cast

from pheroos.governance._schema.certificate import CERTIFICATE_CONTRACTS
from pheroos.governance._schema.commit import COMMIT_CONTRACTS
from pheroos.governance._schema.common import (
    CommitWireBinding,
    CommitWireContract,
    _validate_canonical_set,
    _validate_lexical_set,
    _validate_noncritical_envelope_extensions,
    envelope_schema,
)
from pheroos.governance._schema.distributed import DISTRIBUTED_CONTRACTS
from pheroos.governance._schema.foundation import FOUNDATION_CONTRACTS
from pheroos.governance._schema.hybrid import HYBRID_CONTRACTS
from pheroos.governance._schema.support import SUPPORT_CONTRACTS
from pheroos.protocol.commit_models import COMMIT_PROFILES_BY_ASSURANCE
from pheroos.protocol.commit_wire import CommitWireError, canonical_commit_payload
from pheroos.protocol.schema_validation import validate_json_schema


COMMIT_WIRE_CONTRACTS: tuple[CommitWireContract, ...] = (
    *FOUNDATION_CONTRACTS,
    *COMMIT_CONTRACTS,
    *SUPPORT_CONTRACTS,
    *HYBRID_CONTRACTS,
    *CERTIFICATE_CONTRACTS,
    *DISTRIBUTED_CONTRACTS,
)


def _contract_map(
    contracts: tuple[CommitWireContract, ...],
) -> MappingProxyType[str, CommitWireContract]:
    result: dict[str, CommitWireContract] = {}
    for contract in contracts:
        if contract.schema_name in result:
            raise RuntimeError(
                f"duplicate static Commit Wire contract: {contract.schema_name}"
            )
        result[contract.schema_name] = contract
    return MappingProxyType(result)


COMMIT_WIRE_CONTRACTS_BY_SCHEMA = _contract_map(COMMIT_WIRE_CONTRACTS)


_CANONICAL_TEXT_SET_FIELDS: tuple[str, ...] = (
    "reason_codes",
    "next_required_inputs",
    "unmet_gates",
    "rationale_codes",
    "required_categories",
    "covered_categories",
    "missing_categories",
    "active_support_clusters",
    "conflicting_candidates",
    "required_challenge_categories",
    "publishable_outcomes",
    "executable_outcomes",
    "substantive_candidate_ids",
    "tied_candidate_ids",
    "assessment_reason_codes",
    "blocked_reason_codes",
    "finality_reason_codes",
    "invalid_reason_codes",
    "safety_violation_reason_codes",
    "last_assessment_reason_codes",
    "issuer_attestation_refs",
)

_LEXICAL_FINGERPRINT_SET_FIELDS: tuple[str, ...] = (
    "rebuttal_observation_fingerprints",
    "result_observation_fingerprints",
    "challenge_fingerprints",
    "positive_observation_fingerprints",
    "counter_observation_fingerprints",
    "disposition_fingerprints",
    "active_counter_observation_fingerprints",
    "resolved_counter_observation_fingerprints",
    "blocking_critical_counter_observation_fingerprints",
    "risk_input_fingerprints",
    "included_lease_fingerprints",
    "excluded_lease_fingerprints",
    "conflicting_lease_fingerprints",
    "blocker_references",
    "equivocation_finding_ids",
    "replay_conflict_references",
)


def commit_schema_document() -> dict[str, Any]:
    """Build the v1 artifact from the immutable branch contracts."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/commit.schema.json",
        "title": "PheroOS Commit Wire ABI v1",
        "description": (
            "Strict authority envelopes are selected by schema. Namespaced "
            "non-critical envelope metadata is explicitly non-authoritative; "
            "critical or unnamespaced additions fail closed."
        ),
        "discriminator": {"propertyName": "schema"},
        "oneOf": [
            envelope_schema(
                contract.schema_name,
                contract.payload_schema(),
                profiles=contract.profiles,
            )
            for contract in COMMIT_WIRE_CONTRACTS
        ],
    }


def validate_commit_wire_document(record: object) -> list[str]:
    """Validate shape, canonical encoding, bindings, and branch semantics."""

    errors = validate_json_schema(record, commit_schema_document())
    if errors:
        return errors
    components = _validated_commit_wire_components(cast(Mapping[str, Any], record))
    if isinstance(components, list):
        return components
    payload, schema_name, profile, _version = components
    contract = COMMIT_WIRE_CONTRACTS_BY_SCHEMA[str(schema_name)]
    semantic: list[str] = []
    _validate_commit_wire_binding(
        contract,
        payload=payload,
        profile=profile,
        errors=semantic,
    )
    _validate_commit_wire_sets(payload, errors=semantic)
    semantic.extend(contract.validator(payload, str(profile)))
    return semantic


def _validated_commit_wire_components(
    record: Mapping[str, Any],
) -> tuple[Mapping[str, Any], object, object, object] | list[str]:
    metadata_errors = _validate_noncritical_envelope_extensions(record)
    if metadata_errors:
        return metadata_errors

    payload = cast(Mapping[str, Any], record.get("payload"))
    schema_name = record.get("schema")
    profile = record.get("profile")
    version = record.get("version")
    try:
        canonical_commit_payload(
            payload,
            schema=str(schema_name),
            profile=str(profile),
            version=str(version),
        )
    except CommitWireError as exc:
        return [f"$: {exc}"]
    return payload, schema_name, profile, version


def _validate_commit_wire_binding(
    contract: CommitWireContract,
    *,
    payload: Mapping[str, Any],
    profile: object,
    errors: list[str],
) -> None:
    if contract.binding is not CommitWireBinding.UNBOUND:
        if payload.get("profile") != profile:
            errors.append("$.payload.profile: envelope profile mismatch")
        if contract.binding is CommitWireBinding.PROFILE_AND_ASSURANCE:
            assurance = payload.get("assurance")
            allowed_profiles = COMMIT_PROFILES_BY_ASSURANCE.get(str(assurance))
            if allowed_profiles is None or profile not in allowed_profiles:
                errors.append("$.payload.assurance: profile/assurance mismatch")


def _validate_commit_wire_sets(
    payload: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
    for field_name in _CANONICAL_TEXT_SET_FIELDS:
        values = payload.get(field_name)
        if isinstance(values, list):
            _validate_canonical_set(
                values,
                path=f"$.payload.{field_name}",
                errors=errors,
            )

    for field_name in _LEXICAL_FINGERPRINT_SET_FIELDS:
        values = payload.get(field_name)
        if isinstance(values, list):
            _validate_lexical_set(
                values,
                path=f"$.payload.{field_name}",
                errors=errors,
            )


__all__: tuple[str, ...] = ()
