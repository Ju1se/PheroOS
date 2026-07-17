from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    SUPPORTED_COMMIT_PROFILES,
)
from pheroos.governance.errors import GovernanceError

from pheroos.governance._schema.common import (
    CommitWireBinding,
    CommitWireContract,
    authority_integer_schema,
    canonical_text_schema,
    canonical_text_set_schema,
    commit_binding_properties,
    fingerprint_schema,
    governance_authority_schema,
    optional_fingerprint_schema,
    optional_text_schema,
    profile_agnostic,
    strict_object_schema,
)


def _validate_local_commit_receipt_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    from pheroos.governance.authority import AuthorityLevel
    from pheroos.governance.certificate import LocalCommitReceipt
    from pheroos.governance.commit_state import AuthorityScope
    from pheroos.protocol.commit_models import CommitAssurance

    values = dict(payload)
    try:
        values["assurance"] = CommitAssurance(values["assurance"])
        values["authority_scope"] = AuthorityScope(values["authority_scope"])
        values["authority"] = AuthorityLevel(values["authority"])
        LocalCommitReceipt(**values)
    except (GovernanceError, TypeError, ValueError):
        return ["$.payload: local receipt typed lineage is invalid"]
    return []

def _validate_evidence_certificate_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    # The public portable decoder reconstructs both roots and validates every
    # typed leaf without trusting an in-process issuance sentinel.
    from pheroos.governance.certificate import (
        evidence_commit_certificate_from_payload,
    )

    try:
        evidence_commit_certificate_from_payload(payload)
    except (GovernanceError, TypeError, ValueError):
        return ["$.payload: evidence certificate roots or typed lineage are invalid"]
    return []

def _validate_outcome_certificate_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    # OutcomeCertificate has a different discriminator and decoder from an
    # evidence certificate.  Its decoder also enforces non-commit authority
    # semantics and reconstructs its body/envelope roots.
    from pheroos.governance.certificate import outcome_certificate_from_payload

    try:
        outcome_certificate_from_payload(payload)
    except (GovernanceError, TypeError, ValueError):
        return ["$.payload: outcome certificate roots or typed lineage are invalid"]
    return []

def _validate_commit_output_authorization_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    gates = payload["gates"]
    if not gates:
        errors.append("$.payload.gates: at least one authority gate is required")
    elif payload["authorized"] is not all(gates.values()):
        errors.append("$.payload.authorized: gate conjunction mismatch")
    if bool(payload["distributed_state_ref"]) is not bool(
        payload["distributed_conflict_root"]
    ):
        errors.append("$.payload: distributed state/conflict roots must co-exist")
    authority_refs = (
        payload["certificate_ref"],
        payload["policy_ref"],
        payload["threshold_ref"],
        payload["stop_resolution_ref"],
        payload["permission_ref"],
    )
    if payload["action"] == "deliver":
        if any((*authority_refs, payload["distributed_state_ref"])):
            errors.append("$.payload: delivery cannot claim action authority refs")
    elif payload["authorized"] and not all(authority_refs):
        errors.append(
            "$.payload: authorized publish/execute requires every authority ref"
        )
    return errors

def _certificate_lineage_properties(
    *,
    allow_empty_contextual_roots: bool = False,
) -> dict[str, Any]:
    contextual_root = (
        optional_fingerprint_schema()
        if allow_empty_contextual_roots
        else fingerprint_schema()
    )
    return {
        "assessment_root": contextual_root,
        "candidate_challenge_root": contextual_root,
        "candidate_evidence_root": contextual_root,
        "candidate_lease_root": contextual_root,
        "challenge_root": contextual_root,
        "claim_fingerprint": contextual_root,
        "context_root": contextual_root,
        "evidence_root": contextual_root,
        "lease_root": contextual_root,
        "membership_epoch_state_root": contextual_root,
        "membership_root": fingerprint_schema(),
        "membership_snapshot_root": contextual_root,
        "output_payload_fingerprint": fingerprint_schema(),
        "permission_root": contextual_root,
        "replay_root": fingerprint_schema(),
        "replay_state_root": fingerprint_schema(),
        "risk_assessment_root": fingerprint_schema(),
        "risk_chain_state_root": contextual_root,
        "risk_policy_root": contextual_root,
        "stop_resolution_root": contextual_root,
        "support_replay_root": contextual_root,
        "support_replay_state_root": contextual_root,
        "threshold_root": fingerprint_schema(),
        "window_root": fingerprint_schema(),
        "window_state_root": fingerprint_schema(),
    }

def _certificate_header_properties() -> dict[str, Any]:
    return {
        "canonicalization": {"const": COMMIT_CANONICAL_VERSION},
        "hash_algorithm": {"const": "sha256"},
        "wire_version": {"const": COMMIT_WIRE_VERSION},
    }

def _certificate_issuer_properties() -> dict[str, Any]:
    return {
        "authority": governance_authority_schema(),
        "issued_at_step": authority_integer_schema(),
        "issuer_id": canonical_text_schema(),
        "provenance": canonical_text_schema(),
        "trace_event_id": canonical_text_schema(),
    }

def local_commit_receipt_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            **_certificate_header_properties(),
            **_certificate_lineage_properties(),
            **_certificate_issuer_properties(),
            "assurance": {
                "enum": ["certified", "distributed", "evidence_bound"]
            },
            "authority_scope": {"const": "governance_local"},
            "candidate_id": canonical_text_schema(),
            "receipt_id": canonical_text_schema(),
            "receipt_version": {"const": "pheroos-local-commit-receipt-v1"},
            "schema_discriminator": {"const": "local_commit_receipt"},
        }
    )

def evidence_commit_certificate_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            **_certificate_header_properties(),
            **_certificate_lineage_properties(),
            **_certificate_issuer_properties(),
            "assurance": {"enum": ["certified", "distributed"]},
            "authority_scope": {"const": "certified"},
            "candidate_id": canonical_text_schema(),
            "certificate_body_root": fingerprint_schema(),
            "certificate_id": canonical_text_schema(),
            "certificate_root": fingerprint_schema(),
            "certificate_version": {
                "const": "pheroos-evidence-commit-certificate-v1"
            },
            "issuer_attestation_refs": canonical_text_set_schema(minimum=1),
            "local_receipt_ref": fingerprint_schema(),
            "schema_discriminator": {"const": "evidence_commit_certificate"},
        }
    )

def outcome_certificate_payload_schema() -> dict[str, Any]:
    schema = strict_object_schema(
        {
            **commit_binding_properties(),
            **_certificate_header_properties(),
            **_certificate_lineage_properties(
                allow_empty_contextual_roots=True,
            ),
            **_certificate_issuer_properties(),
            "authoritative_commit": {"type": "boolean"},
            "authority_scope": {
                "enum": [
                    "certified",
                    "denial",
                    "distributed",
                    "governance_local",
                    "none",
                ]
            },
            "candidate_id": optional_text_schema(),
            "certificate_body_root": fingerprint_schema(),
            "certificate_id": canonical_text_schema(),
            "certificate_root": fingerprint_schema(),
            "certificate_version": {"const": "pheroos-outcome-certificate-v1"},
            "commit_certificate_ref": optional_fingerprint_schema(),
            "epistemically_committed": {"type": "boolean"},
            "issuer_attestation_refs": canonical_text_set_schema(),
            "outcome_kind": {
                "enum": [
                    "advisory",
                    "blocked",
                    "evidence_commit",
                    "finality_unavailable",
                    "invalid",
                    "safe_fallback",
                    "safety_violation",
                ]
            },
            "outcome_ref": fingerprint_schema(),
            "schema_discriminator": {"const": "outcome_certificate"},
        }
    )
    schema["allOf"] = [
        {
            "if": {
                "properties": {"outcome_kind": {"const": "evidence_commit"}},
                "required": ["outcome_kind"],
            },
            "then": {
                "properties": {
                    "authoritative_commit": {"const": True},
                    "candidate_id": canonical_text_schema(),
                    "claim_fingerprint": fingerprint_schema(),
                    "commit_certificate_ref": fingerprint_schema(),
                    "epistemically_committed": {"const": True},
                },
                "oneOf": [
                    {
                        "properties": {
                            "assurance": {"const": "evidence_bound"},
                            "authority_scope": {"const": "governance_local"},
                        },
                        "required": ["assurance", "authority_scope"],
                    },
                    {
                        "properties": {
                            "assurance": {"const": "certified"},
                            "authority_scope": {"const": "certified"},
                        },
                        "required": ["assurance", "authority_scope"],
                    },
                    {
                        "properties": {
                            "assurance": {"const": "distributed"},
                            "authority_scope": {"const": "distributed"},
                        },
                        "required": ["assurance", "authority_scope"],
                    },
                ],
            },
            "else": {
                "properties": {
                    "authoritative_commit": {"const": False},
                    "commit_certificate_ref": {"const": ""},
                    "epistemically_committed": {"const": False},
                },
                "oneOf": [
                    {
                        "properties": {
                            "authority_scope": {"const": "denial"},
                            "outcome_kind": {"const": "blocked"},
                        },
                        "required": ["authority_scope", "outcome_kind"],
                    },
                    {
                        "properties": {
                            "authority_scope": {"const": "none"},
                            "outcome_kind": {
                                "enum": [
                                    "advisory",
                                    "finality_unavailable",
                                    "invalid",
                                    "safe_fallback",
                                    "safety_violation",
                                ]
                            },
                        },
                        "required": ["authority_scope", "outcome_kind"],
                    },
                ],
            },
        },
        {
            "if": {
                "properties": {
                    "assurance": {"enum": ["certified", "distributed"]}
                },
                "required": ["assurance"],
            },
            "then": {
                "properties": {
                    "issuer_attestation_refs": canonical_text_set_schema(
                        minimum=1
                    )
                }
            },
            "else": {
                "properties": {
                    "issuer_attestation_refs": {
                        **canonical_text_set_schema(),
                        "maxItems": 0,
                    }
                }
            },
        },
        {
            "if": {
                "properties": {"outcome_kind": {"const": "safe_fallback"}},
                "required": ["outcome_kind"],
            },
            "then": {
                "properties": {
                    "candidate_id": canonical_text_schema(),
                    "claim_fingerprint": fingerprint_schema(),
                }
            },
        },
    ]
    return schema

def commit_output_authorization_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "action": {"enum": ["deliver", "execute", "publish"]},
            "authorized": {"type": "boolean"},
            "certificate_ref": optional_fingerprint_schema(),
            "distributed_conflict_root": optional_fingerprint_schema(),
            "distributed_state_ref": optional_fingerprint_schema(),
            "gates": {
                "type": "object",
                "minProperties": 1,
                "patternProperties": {
                    r"^[a-z][a-z0-9_]*$": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            "outcome_ref": optional_fingerprint_schema(),
            "output_payload_fingerprint": optional_fingerprint_schema(),
            "permission_ref": optional_fingerprint_schema(),
            "policy_ref": optional_fingerprint_schema(),
            "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
            "reason_codes": canonical_text_set_schema(minimum=1),
            "stop_resolution_ref": optional_fingerprint_schema(),
            "threshold_ref": optional_fingerprint_schema(),
        }
    )


CERTIFICATE_CONTRACTS: tuple[CommitWireContract, ...] = (
    CommitWireContract(
        "pheroos-local-commit-receipt-v1",
        local_commit_receipt_payload_schema,
        profile_agnostic(_validate_local_commit_receipt_semantics),
    ),
    CommitWireContract(
        "pheroos-evidence-commit-certificate-v1",
        evidence_commit_certificate_payload_schema,
        profile_agnostic(_validate_evidence_certificate_semantics),
    ),
    CommitWireContract(
        "pheroos-outcome-certificate-v1",
        outcome_certificate_payload_schema,
        profile_agnostic(_validate_outcome_certificate_semantics),
    ),
    CommitWireContract(
        "pheroos-commit-output-authorization-v1",
        commit_output_authorization_payload_schema,
        profile_agnostic(_validate_commit_output_authorization_semantics),
        binding=CommitWireBinding.PROFILE,
    ),
)

__all__: tuple[str, ...] = ()
