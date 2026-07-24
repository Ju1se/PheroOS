"""Draft JSON Schema and strict reader for portable scoped-authority v2 records.

The document is a closed union over the portable records already owned by the
StateStore v2, Authority Session v2, and Baseline Output v2 facades.  It does
not make a wire record authoritative: current StateStore inclusion and the
applicable Governance operation remain the authority boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
import json
import math
from typing import Any, NoReturn, TypeAlias, cast
import unicodedata

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
    MAX_GOVERNANCE_AUTHORITY_READ_SET_ENTRIES_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
)

from pheroos.governance.authority_session_v2 import (
    GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2,
    GOVERNANCE_ISSUER_GRANT_SCHEMA_V2,
    GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2,
    ISSUER_GRANT_VERIFICATION_SCHEMA_V2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    IssuerGrantVerificationV2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_DOMAIN_SCHEMA_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2,
    GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2,
    GOVERNANCE_COMMIT_BATCH_SCHEMA_V2,
    GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2,
    GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2,
    GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2,
    GOVERNANCE_COMMIT_VIEW_SCHEMA_V2,
    GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2,
    GOVERNANCE_FAILURE_SCHEMA_V2,
    GOVERNANCE_HEAD_SCHEMA_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2,
    MAX_GOVERNANCE_TRACE_EVENTS_V2,
    PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitInclusionProofV2,
    GovernanceCommitPositionObservationV2,
    GovernanceCommitPositionV2,
    GovernanceCommitReceiptV2,
    GovernanceCommitViewV2,
    GovernanceCommittedTransitionV2,
    GovernanceDomainSealV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceTraceBatchV2,
    PreparedGovernanceTransitionV2,
)
from pheroos.governance.baseline_output_v2 import (
    ACTION_PERMISSION_SCHEMA_V2,
    BASELINE_OUTPUT_REQUEST_SCHEMA_V2,
    BASELINE_OUTPUT_RESULT_SCHEMA_V2,
    ActionPermissionDispositionV2,
    ActionPermissionV2,
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    BaselineOutputTerminalStatusV2,
)


AUTHORITY_SCHEMA_V2 = "pheroos-authority-schema-v2"
AUTHORITY_SCHEMA_V2_ID = "https://pheroos.dev/schemas/authority-v2.schema.json"
_PROTOCOL_SCHEMA_V3_ID = "https://pheroos.dev/schemas/protocol-v3.schema.json"
_TRACE_SCHEMA_ID = "https://pheroos.dev/schemas/trace.schema.json"
_ROOT_PATTERN = "^sha256:[0-9a-f]{64}$"


AuthorityWireRecordV2: TypeAlias = (
    GovernanceAuthorityReadSetV2
    | AuthorityDomainV2
    | GovernanceHeadV2
    | PreparedGovernanceTransitionV2
    | GovernanceTraceBatchV2
    | GovernanceDomainSealV2
    | GovernanceCommitBatchV2
    | GovernanceCommitReceiptV2
    | GovernanceCommitInclusionProofV2
    | GovernanceCommittedTransitionV2
    | GovernanceCommitPositionObservationV2
    | GovernanceFailureV2
    | GovernanceCommitAttemptV2
    | GovernanceCommitViewV2
    | GovernanceIssuerGrantV2
    | IssuerGrantVerificationV2
    | GovernanceVerifiedSignalRequestV2
    | GovernanceDomainRetirementRequestV2
    | BaselineOutputRequestV2
    | ActionPermissionV2
    | BaselineOutputResultV2
)


class AuthorityWireValidationCodeV2(StrEnum):
    """Closed Draft reader diagnostics; these values do not grant authority."""

    INVALID_JSON = "authority_wire_invalid_json"
    NOT_OBJECT = "authority_wire_not_object"
    SCHEMA_MISSING = "authority_wire_schema_missing"
    SCHEMA_UNSUPPORTED = "authority_wire_schema_unsupported"
    RECORD_INVALID = "authority_wire_record_invalid"


class AuthorityWireValidationErrorV2(ValueError):
    """Typed fail-closed error from the authority-v2 wire reader."""

    __slots__ = ("code", "path", "detail")

    def __init__(
        self,
        code: AuthorityWireValidationCodeV2,
        path: str,
        detail: str,
    ) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code.value}:{path}:{detail}")


def authority_schema_v2() -> dict[str, Any]:
    """Return the complete Draft authority-v2 portable-record union schema."""

    definitions = _authority_definitions_v2()
    branches = (
        "authorityReadSet",
        "authorityDomain",
        "governanceHead",
        "preparedTransition",
        "traceBatch",
        "domainSeal",
        "commitBatch",
        "commitReceipt",
        "commitInclusionProof",
        "committedTransition",
        "commitPositionObservation",
        "governanceFailure",
        "commitAttempt",
        "commitView",
        "issuerGrant",
        "issuerGrantVerification",
        "verifiedSignalRequest",
        "domainRetirementRequest",
        "baselineOutputRequest",
        "actionPermission",
        "baselineOutputResult",
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": AUTHORITY_SCHEMA_V2_ID,
        "title": "PheroOS Draft portable scoped-authority v2 record",
        "oneOf": [{"$ref": f"#/$defs/{name}"} for name in branches],
        "$defs": definitions,
    }


def read_authority_wire_record_v2(payload: object) -> AuthorityWireRecordV2:
    """Read one exact mapping into its existing canonical portable record type."""

    if type(payload) is not dict:
        raise AuthorityWireValidationErrorV2(
            AuthorityWireValidationCodeV2.NOT_OBJECT,
            "",
            "authority wire record must be an exact JSON object",
        )
    schema = payload.get("schema")
    if schema is None:
        raise AuthorityWireValidationErrorV2(
            AuthorityWireValidationCodeV2.SCHEMA_MISSING,
            "/schema",
            "authority wire record requires an explicit schema discriminator",
        )
    if type(schema) is not str or schema not in _AUTHORITY_WIRE_READERS_V2:
        raise AuthorityWireValidationErrorV2(
            AuthorityWireValidationCodeV2.SCHEMA_UNSUPPORTED,
            "/schema",
            "authority wire schema discriminator is unsupported",
        )
    try:
        record = _AUTHORITY_WIRE_READERS_V2[schema](payload)
        _reject_nonfinite_tree(payload)
    except AuthorityWireValidationErrorV2:
        raise
    except (TypeError, ValueError) as exc:
        raise AuthorityWireValidationErrorV2(
            AuthorityWireValidationCodeV2.RECORD_INVALID,
            "",
            str(exc),
        ) from exc
    return record


def validate_authority_wire_record_v2(payload: object) -> None:
    """Validate one mapping with the same semantic dispatch as the typed reader."""

    read_authority_wire_record_v2(payload)


def loads_authority_wire_record_v2(
    value: str | bytes | bytearray,
) -> AuthorityWireRecordV2:
    """Strictly decode UTF-8 JSON, rejecting duplicate keys and non-finite values."""

    text = _require_json_text(value)
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_number,
        )
    except AuthorityWireValidationErrorV2:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AuthorityWireValidationErrorV2(
            AuthorityWireValidationCodeV2.INVALID_JSON,
            "",
            "authority wire JSON is invalid",
        ) from exc
    return read_authority_wire_record_v2(payload)


def _authority_definitions_v2() -> dict[str, Any]:
    root = {"type": "string", "pattern": _ROOT_PATTERN}
    text = {"type": "string", "minLength": 1}
    epoch = _exact_integer(0, MAX_AUTHORITY_REVISION_V2)
    nullable_root = _nullable(root)
    nullable_text = _nullable(text)

    definitions: dict[str, Any] = {
        "canonicalJson": _canonical_json_schema(),
        "readPrecondition": _closed(
            {
                "stream_ref": text,
                "expected_revision": epoch,
                "expected_root": root,
            }
        ),
        "finalHead": _closed(
            {"stream_ref": text, "revision": epoch, "head_root": root}
        ),
        "verifiedSignalProposal": _closed(
            {
                "candidate_ref": text,
                "evidence_root": root,
                "provenance_ref": root,
                "signal_ref": text,
                "signal_root": root,
                "signal_transition_id": text,
                "source_ref": text,
            }
        ),
        "stopResolution": _closed(
            {
                "action_ref": text,
                "blocked": {"type": "boolean"},
                "provenance_ref": root,
                "reason_ref": text,
            }
        ),
    }
    definitions.update(
        {
            "authorityReadSet": _record(
                GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
                {
                    "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                    "entries": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_GOVERNANCE_AUTHORITY_READ_SET_ENTRIES_V2,
                        "uniqueItems": True,
                        "items": {"$ref": "#/$defs/readPrecondition"},
                    },
                },
            ),
            "authorityDomain": _record(
                AUTHORITY_DOMAIN_SCHEMA_V2,
                {
                    "policy_version": {"const": AUTHORITY_POLICY_VERSION_V2},
                    "profile": {
                        "enum": [
                            AUTHORITY_LOCAL_PROFILE_V2,
                            AUTHORITY_AUTHENTICATED_PROFILE_V2,
                        ]
                    },
                    "wire_version": {"const": AUTHORITY_WIRE_VERSION_V2},
                    "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                    "ledger_version": {"const": AUTHORITY_LEDGER_VERSION_V2},
                    "state_store_version": {"const": GOVERNANCE_STATE_STORE_VERSION_V2},
                    "trace_batch_version": {"const": GOVERNANCE_TRACE_BATCH_VERSION_V2},
                    "read_set_version": {
                        "const": GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2
                    },
                    "scope_ref": text,
                    "domain_root": root,
                },
            ),
            "governanceHead": _record(
                GOVERNANCE_HEAD_SCHEMA_V2,
                {
                    "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                    "ledger_version": {"const": AUTHORITY_LEDGER_VERSION_V2},
                    "domain_root": root,
                    "scope_ref": text,
                    "stream_ref": text,
                    "revision": epoch,
                    "parent_root": root,
                    "state_root": root,
                    "transition_id": text,
                    "batch_root": root,
                    "head_root": root,
                },
            ),
            "preparedTransition": _record(
                PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2,
                {
                    "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                    "ledger_version": {"const": AUTHORITY_LEDGER_VERSION_V2},
                    "domain_root": root,
                    "scope_ref": text,
                    "stream_ref": text,
                    "transition_id": text,
                    "expected_revision": epoch,
                    "expected_root": root,
                    "read_set_root": root,
                    "state_records": {
                        "type": "object",
                        "additionalProperties": {"$ref": "#/$defs/canonicalJson"},
                    },
                    "state_root": root,
                    "transition_root": root,
                },
            ),
            "traceBatch": _record(
                GOVERNANCE_TRACE_BATCH_VERSION_V2,
                {
                    "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                    "domain_root": root,
                    "scope_ref": text,
                    "stream_ref": text,
                    "transition_id": text,
                    "events": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_GOVERNANCE_TRACE_EVENTS_V2,
                        "items": {"$ref": _TRACE_SCHEMA_ID},
                    },
                    "trace_root": root,
                },
            ),
            "domainSeal": _record(
                GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2,
                {
                    "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                    "ledger_version": {"const": AUTHORITY_LEDGER_VERSION_V2},
                    "domain_root": root,
                    "scope_ref": text,
                    "transition_id": text,
                    "expected_revision": epoch,
                    "expected_root": root,
                    "final_heads": {
                        "type": "array",
                        "maxItems": MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2,
                        "uniqueItems": True,
                        "items": {"$ref": "#/$defs/finalHead"},
                    },
                    "final_heads_root": root,
                    "seal_root": root,
                },
            ),
        }
    )

    commit_batch = _record(
        GOVERNANCE_COMMIT_BATCH_SCHEMA_V2,
        {
            "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
            "ledger_version": {"const": AUTHORITY_LEDGER_VERSION_V2},
            "domain": {"$ref": "#/$defs/authorityDomain"},
            "domain_root": root,
            "scope_ref": text,
            "stream_ref": text,
            "transition_id": text,
            "kind": {"enum": ["transition", "seal"]},
            "read_set": {"$ref": "#/$defs/authorityReadSet"},
            "read_set_root": root,
            "transition": _nullable({"$ref": "#/$defs/preparedTransition"}),
            "transition_root": nullable_root,
            "seal": _nullable({"$ref": "#/$defs/domainSeal"}),
            "seal_root": nullable_root,
            "trace_batch": {"$ref": "#/$defs/traceBatch"},
            "trace_root": root,
            "batch_root": root,
        },
    )
    commit_batch["allOf"] = [
        {
            "if": {"properties": {"kind": {"const": "transition"}}},
            "then": {
                "properties": {
                    "transition": {"$ref": "#/$defs/preparedTransition"},
                    "transition_root": root,
                    "seal": {"type": "null"},
                    "seal_root": {"type": "null"},
                }
            },
        },
        {
            "if": {"properties": {"kind": {"const": "seal"}}},
            "then": {
                "properties": {
                    "transition": {"type": "null"},
                    "transition_root": {"type": "null"},
                    "seal": {"$ref": "#/$defs/domainSeal"},
                    "seal_root": root,
                }
            },
        },
    ]
    definitions["commitBatch"] = commit_batch
    definitions.update(
        {
            "commitReceipt": _record(
                GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2,
                _bound_commit_properties(
                    root,
                    text,
                    epoch,
                    {
                        "revision": epoch,
                        "parent_root": root,
                        "head_root": root,
                        "state_root": root,
                        "read_set_root": root,
                        "trace_root": root,
                        "batch_root": root,
                        "receipt_root": root,
                    },
                    ledger=True,
                ),
            ),
            "commitInclusionProof": _record(
                GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2,
                _bound_commit_properties(
                    root,
                    text,
                    epoch,
                    {
                        "revision": epoch,
                        "batch_root": root,
                        "receipt_root": root,
                        "head_root": root,
                        "inclusion_root": root,
                    },
                    ledger=True,
                ),
            ),
            "committedTransition": _record(
                GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2,
                {
                    "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                    "ledger_version": {"const": AUTHORITY_LEDGER_VERSION_V2},
                    "batch": {"$ref": "#/$defs/commitBatch"},
                    "receipt": {"$ref": "#/$defs/commitReceipt"},
                    "inclusion_proof": {"$ref": "#/$defs/commitInclusionProof"},
                    "committed_transition_root": root,
                },
            ),
            "commitPositionObservation": _record(
                GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2,
                _bound_commit_properties(
                    root,
                    text,
                    epoch,
                    {
                        "receipt_root": root,
                        "observed_revision": epoch,
                        "observed_head_root": root,
                        "position": {
                            "enum": [item.value for item in GovernanceCommitPositionV2]
                        },
                        "seal_root": nullable_root,
                        "observation_root": root,
                    },
                    ledger=True,
                ),
            ),
            "governanceFailure": _record(
                GOVERNANCE_FAILURE_SCHEMA_V2,
                {
                    "code": {
                        "enum": [item.value for item in AuthorityDiagnosticCodeV2]
                    },
                    "path": {"type": "string"},
                    "stage": {
                        "enum": [item.value for item in GovernanceFailureStageV2]
                    },
                    "failure_root": root,
                },
            ),
        }
    )
    result_properties = _bound_commit_properties(
        root,
        text,
        epoch,
        {
            "disposition": {
                "enum": [item.value for item in GovernanceCommitDispositionV2]
            },
            "failure": _nullable({"$ref": "#/$defs/governanceFailure"}),
            "committed_transition": _nullable({"$ref": "#/$defs/committedTransition"}),
            "position_observation": _nullable(
                {"$ref": "#/$defs/commitPositionObservation"}
            ),
            "attempt_root": root,
        },
        ledger=False,
    )
    definitions["commitAttempt"] = _record(
        GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2,
        result_properties,
    )
    view_properties = _bound_commit_properties(
        root,
        text,
        epoch,
        {
            "expected_receipt_root": nullable_root,
            "disposition": {
                "enum": [item.value for item in GovernanceCommitDispositionV2]
            },
            "failure": _nullable({"$ref": "#/$defs/governanceFailure"}),
            "committed_transition": _nullable({"$ref": "#/$defs/committedTransition"}),
            "position_observation": _nullable(
                {"$ref": "#/$defs/commitPositionObservation"}
            ),
            "observed_revision": _nullable(epoch),
            "observed_head_root": nullable_root,
            "view_root": root,
        },
        ledger=False,
    )
    definitions["commitView"] = _record(
        GOVERNANCE_COMMIT_VIEW_SCHEMA_V2,
        view_properties,
    )

    definitions.update(_session_definitions(root, text, epoch))
    definitions.update(
        _baseline_definitions(root, text, epoch, nullable_root, nullable_text)
    )
    return definitions


def _session_definitions(
    root: dict[str, Any],
    text: dict[str, Any],
    epoch: dict[str, Any],
) -> dict[str, Any]:
    ref_array = {
        "type": "array",
        "uniqueItems": True,
        "items": text,
    }
    return {
        "issuerGrant": _record(
            GOVERNANCE_ISSUER_GRANT_SCHEMA_V2,
            {
                "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                "domain_root": root,
                "scope_ref": text,
                "issuer_ref": text,
                "grant_ref": text,
                "grant_binding_ref": root,
                "operations": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "enum": [item.value for item in GovernanceIssuerOperationV2]
                    },
                },
                "target_refs": ref_array,
                "action_refs": ref_array,
                "issued_epoch": epoch,
                "not_before_epoch": epoch,
                "expires_at_epoch": epoch,
                "revocation_generation": epoch,
                "grant_root": root,
            },
        ),
        "issuerGrantVerification": _record(
            ISSUER_GRANT_VERIFICATION_SCHEMA_V2,
            {
                "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                "grant_root": root,
                "grant_binding_ref": root,
                "verifier_ref": text,
                "accepted": {"type": "boolean"},
                "verified_epoch": epoch,
                "verification_root": root,
            },
        ),
        "verifiedSignalRequest": _record(
            GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2,
            {
                "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                "domain_root": root,
                "scope_ref": text,
                "run_ref": text,
                "request_ref": text,
                "transition_id": text,
                "signal_ref": text,
                "target_ref": text,
                "signal_root": root,
                "evidence_root": root,
                "status": {"enum": ["verified", "rejected"]},
                "observed_epoch": epoch,
                "stream_ref": text,
                "request_root": root,
            },
        ),
        "domainRetirementRequest": _record(
            GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2,
            {
                "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                "domain_root": root,
                "scope_ref": text,
                "run_ref": text,
                "request_ref": text,
                "transition_id": text,
                "stream_refs": {
                    "type": "array",
                    "maxItems": MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2,
                    "uniqueItems": True,
                    "items": text,
                },
                "reason_ref": text,
                "observed_epoch": epoch,
                "request_root": root,
            },
        ),
    }


def _baseline_definitions(
    root: dict[str, Any],
    text: dict[str, Any],
    epoch: dict[str, Any],
    nullable_root: dict[str, Any],
    nullable_text: dict[str, Any],
) -> dict[str, Any]:
    return {
        "baselineOutputRequest": _record(
            BASELINE_OUTPUT_REQUEST_SCHEMA_V2,
            {
                "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                "domain_root": root,
                "scope_ref": text,
                "run_ref": text,
                "request_ref": text,
                "output_transition_id": text,
                "manifest": {"$ref": _PROTOCOL_SCHEMA_V3_ID},
                "target_ref": text,
                "action_ref": text,
                "proposed_candidate_ref": nullable_text,
                "verified_signals": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"$ref": "#/$defs/verifiedSignalProposal"},
                },
                "stop_resolutions": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"$ref": "#/$defs/stopResolution"},
                },
                "output_payload": {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/$defs/canonicalJson"},
                },
                "observed_epoch": epoch,
                "manifest_stream_ref": text,
                "evidence_stream_ref": text,
                "stop_stream_ref": text,
                "decision_stream_ref": text,
                "permission_stream_ref": text,
                "output_stream_ref": text,
                "output_payload_root": root,
                "request_root": root,
            },
        ),
        "actionPermission": _record(
            ACTION_PERMISSION_SCHEMA_V2,
            {
                "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                "domain_root": root,
                "scope_ref": text,
                "run_ref": text,
                "request_ref": text,
                "request_root": root,
                "permission_transition_id": text,
                "permission_stream_ref": text,
                "manifest_root": root,
                "output_policy_root": root,
                "evidence_root": root,
                "stop_root": root,
                "decision_root": root,
                "target_ref": text,
                "candidate_ref": text,
                "action_ref": text,
                "effect": {"enum": ["publish", "execute"]},
                "terminal_status": {
                    "enum": [item.value for item in BaselineOutputTerminalStatusV2]
                },
                "output_payload_root": root,
                "disposition": {
                    "enum": [item.value for item in ActionPermissionDispositionV2]
                },
                "issued_epoch": epoch,
                "expires_at_epoch": epoch,
                "grant_ref": text,
                "grant_root": root,
                "grant_binding_ref": root,
                "permission_root": root,
            },
        ),
        "baselineOutputResult": _record(
            BASELINE_OUTPUT_RESULT_SCHEMA_V2,
            {
                "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
                "domain_root": root,
                "scope_ref": text,
                "run_ref": text,
                "request_ref": text,
                "request_root": root,
                "output_transition_id": text,
                "output_payload_root": root,
                "terminal_status": _nullable(
                    {"enum": [item.value for item in BaselineOutputTerminalStatusV2]}
                ),
                "candidate_ref": nullable_text,
                "delivery_disposition": {
                    "enum": [item.value for item in BaselineOutputDeliveryDispositionV2]
                },
                "action_disposition": {
                    "enum": [item.value for item in BaselineOutputActionDispositionV2]
                },
                "permission_root": root,
                "authorization": _nullable({"$ref": "#/$defs/actionPermission"}),
                "commit_attempt": {"$ref": "#/$defs/commitAttempt"},
                "result_root": root,
            },
        ),
    }


def _bound_commit_properties(
    root: dict[str, Any],
    text: dict[str, Any],
    _epoch: dict[str, Any],
    extra: dict[str, Any],
    *,
    ledger: bool,
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
    }
    if ledger:
        properties["ledger_version"] = {"const": AUTHORITY_LEDGER_VERSION_V2}
    properties.update(
        {
            "domain_root": root,
            "scope_ref": text,
            "stream_ref": text,
            "transition_id": text,
        }
    )
    properties.update(extra)
    return properties


def _record(schema: str, properties: dict[str, Any]) -> dict[str, Any]:
    return _closed({"schema": {"const": schema}, **properties})


def _closed(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(properties),
        "properties": properties,
        "additionalProperties": False,
    }


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"oneOf": [{"type": "null"}, schema]}


def _exact_integer(minimum: int, maximum: int) -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": minimum,
        "maximum": maximum,
        "x-pheroos-exact-integer": True,
    }


def _canonical_json_schema() -> dict[str, Any]:
    return {
        "oneOf": [
            {"type": "null"},
            {"type": "boolean"},
            _exact_integer(-(2**53 - 1), 2**53 - 1),
            {"type": "string"},
            {"type": "array", "items": {"$ref": "#/$defs/canonicalJson"}},
            {
                "type": "object",
                "additionalProperties": {"$ref": "#/$defs/canonicalJson"},
            },
        ]
    }


def _require_json_text(value: object) -> str:
    if type(value) is str:
        text = value
    elif isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise AuthorityWireValidationErrorV2(
                AuthorityWireValidationCodeV2.INVALID_JSON,
                "",
                "authority wire JSON must not use a BOM",
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuthorityWireValidationErrorV2(
                AuthorityWireValidationCodeV2.INVALID_JSON,
                "",
                "authority wire JSON must use UTF-8",
            ) from exc
    else:
        raise AuthorityWireValidationErrorV2(
            AuthorityWireValidationCodeV2.INVALID_JSON,
            "",
            "authority wire JSON must be text, bytes, or bytearray",
        )
    if text.startswith("\ufeff"):
        raise AuthorityWireValidationErrorV2(
            AuthorityWireValidationCodeV2.INVALID_JSON,
            "",
            "authority wire JSON must not use a BOM",
        )
    return text


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if unicodedata.normalize("NFC", key) != key:
            raise AuthorityWireValidationErrorV2(
                AuthorityWireValidationCodeV2.INVALID_JSON,
                "",
                "authority wire JSON object keys must already use NFC",
            )
        if key in value:
            raise AuthorityWireValidationErrorV2(
                AuthorityWireValidationCodeV2.INVALID_JSON,
                f"/{key}",
                "authority wire JSON contains a duplicate object key",
            )
        value[key] = item
    return value


def _reject_nonfinite_number(value: str) -> NoReturn:
    raise AuthorityWireValidationErrorV2(
        AuthorityWireValidationCodeV2.INVALID_JSON,
        "",
        f"authority wire JSON does not permit {value}",
    )


def _reject_nonfinite_tree(value: object) -> None:
    if type(value) is float and not math.isfinite(value):
        raise AuthorityWireValidationErrorV2(
            AuthorityWireValidationCodeV2.RECORD_INVALID,
            "",
            "authority wire record does not permit non-finite numbers",
        )
    if isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite_tree(item)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite_tree(item)


def _read_as(
    record_type: type[AuthorityWireRecordV2],
) -> Callable[[object], AuthorityWireRecordV2]:
    return cast(Callable[[object], AuthorityWireRecordV2], record_type.from_dict)


_AUTHORITY_WIRE_READERS_V2: dict[str, Callable[[object], AuthorityWireRecordV2]] = {
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2: _read_as(GovernanceAuthorityReadSetV2),
    AUTHORITY_DOMAIN_SCHEMA_V2: _read_as(AuthorityDomainV2),
    GOVERNANCE_HEAD_SCHEMA_V2: _read_as(GovernanceHeadV2),
    PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2: _read_as(PreparedGovernanceTransitionV2),
    GOVERNANCE_TRACE_BATCH_VERSION_V2: _read_as(GovernanceTraceBatchV2),
    GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2: _read_as(GovernanceDomainSealV2),
    GOVERNANCE_COMMIT_BATCH_SCHEMA_V2: _read_as(GovernanceCommitBatchV2),
    GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2: _read_as(GovernanceCommitReceiptV2),
    GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2: _read_as(
        GovernanceCommitInclusionProofV2
    ),
    GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2: _read_as(
        GovernanceCommittedTransitionV2
    ),
    GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2: _read_as(
        GovernanceCommitPositionObservationV2
    ),
    GOVERNANCE_FAILURE_SCHEMA_V2: _read_as(GovernanceFailureV2),
    GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2: _read_as(GovernanceCommitAttemptV2),
    GOVERNANCE_COMMIT_VIEW_SCHEMA_V2: _read_as(GovernanceCommitViewV2),
    GOVERNANCE_ISSUER_GRANT_SCHEMA_V2: _read_as(GovernanceIssuerGrantV2),
    ISSUER_GRANT_VERIFICATION_SCHEMA_V2: _read_as(IssuerGrantVerificationV2),
    GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2: _read_as(
        GovernanceVerifiedSignalRequestV2
    ),
    GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2: _read_as(
        GovernanceDomainRetirementRequestV2
    ),
    BASELINE_OUTPUT_REQUEST_SCHEMA_V2: _read_as(BaselineOutputRequestV2),
    ACTION_PERMISSION_SCHEMA_V2: _read_as(ActionPermissionV2),
    BASELINE_OUTPUT_RESULT_SCHEMA_V2: _read_as(BaselineOutputResultV2),
}


__all__ = [
    "AUTHORITY_SCHEMA_V2",
    "AUTHORITY_SCHEMA_V2_ID",
    "AuthorityWireRecordV2",
    "AuthorityWireValidationCodeV2",
    "AuthorityWireValidationErrorV2",
    "authority_schema_v2",
    "loads_authority_wire_record_v2",
    "read_authority_wire_record_v2",
    "validate_authority_wire_record_v2",
]
