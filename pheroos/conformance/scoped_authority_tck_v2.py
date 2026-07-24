"""Draft, expected-free artifact contracts for the scoped-authority v2 TCK.

This module describes portable Conformance vectors and reports.  It is not an
adapter server, runtime protocol, plugin surface, or source of authority.  A
subject receives only the expected-free request; the harness retains the
verifier-owned invariant labels from the enclosing case.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from typing import Any, NoReturn, TypeAlias, cast
import unicodedata

from pheroos.governance.authority_schema_v2 import (
    AUTHORITY_SCHEMA_V2_ID,
    AuthorityWireRecordV2,
    AuthorityWireValidationErrorV2,
    read_authority_wire_record_v2,
)
from pheroos.governance.authority_session_v2 import GovernanceIssuerOperationV2
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2

from pheroos.conformance.checks.authority_session_v2_contract import (
    GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2,
    GOVERNANCE_STATE_STORE_TAMPER_CASES_V2,
    GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
)
from pheroos.conformance.checks.baseline_output_v2_contract import (
    GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2,
)


SCOPED_AUTHORITY_TCK_VERSION_V2 = "pheroos-scoped-authority-tck-v2"
SCOPED_AUTHORITY_TCK_SCHEMA_V2 = SCOPED_AUTHORITY_TCK_VERSION_V2
SCOPED_AUTHORITY_TCK_SCHEMA_V2_ID = (
    "https://pheroos.dev/schemas/scoped-authority-tck-v2.schema.json"
)

SCOPED_AUTHORITY_TCK_OPERATIONS_V2 = (
    *(item.value for item in GovernanceIssuerOperationV2),
    "activate_governance_issuer_grant_v2",
    "atomic_commit_v2",
    "bind_governance_issuer_capability_v2",
    "commit_verified_signal_v2",
    "create_domain_v2",
    "create_failure_injected_store_v2",
    "create_store_v2",
    "evaluate_and_commit_baseline_output_v2",
    "issue_action_permission_v2",
    "load_commit_view_v2",
    "load_head_v2",
    "load_state_v2",
    "observe_store_v2",
    "open_baseline_output_authority_session_v2",
    "open_governance_authority_session_v2",
    "restart_store_v2",
    "retire_governance_domain_v2",
    "revoke_governance_issuer_grant_v2",
    "tamper_store_v2",
)

STATE_STORE_TCK_CASE_IDS_V2 = (
    "state_store:closed_registries",
    "state_store:fresh_store",
    "state_store:unknown_scope",
    "state_store:identity_and_history",
    "state_store:multi_read_atomicity",
    "state_store:concurrency",
    "state_store:failure_boundaries",
    "state_store:total_views",
    "state_store:seal",
    "state_store:seal_race",
    "state_store:stream_bound",
    "state_store:restart",
    "state_store:authenticated_restart",
    "state_store:persisted_artifact_mutations",
)
AUTHORITY_SESSION_TCK_CASE_IDS_V2 = (
    "authority_session:local_vertical_slice",
    "authority_session:immutable_mapping_reads",
    "authority_session:store_version_boundary",
    "authority_session:handle_and_request_boundaries",
    "authority_session:revocation_after_session",
    "authority_session:lifecycle_seal_race",
    "authority_session:retirement_closure_and_history",
    "authority_session:authenticated_verifier_boundary",
)
BASELINE_OUTPUT_TCK_CASE_IDS_V2 = (
    "baseline_output:protocol_v3_opt_in",
    "baseline_output:quorum",
    "baseline_output:direct",
    "baseline_output:direct-zero-evidence",
    "baseline_output:fallback-zero-evidence",
    "baseline_output:fallback",
    "baseline_output:blocked",
    "baseline_output:signal_binding_substitutions",
    "baseline_output:required_permission_operations",
    "baseline_output:restart_retry_and_currentness",
    "baseline_output:permission_issuer_revocation",
)
SCOPED_AUTHORITY_TCK_CASE_IDS_V2 = (
    *STATE_STORE_TCK_CASE_IDS_V2,
    *AUTHORITY_SESSION_TCK_CASE_IDS_V2,
    *BASELINE_OUTPUT_TCK_CASE_IDS_V2,
)
SCOPED_AUTHORITY_TCK_FAILURE_STAGES_V2 = (
    *GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2,
    GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
)
SCOPED_AUTHORITY_TCK_INVARIANTS_V2 = (
    *SCOPED_AUTHORITY_TCK_CASE_IDS_V2,
    *(
        f"state_store:failure_stage:{stage}"
        for stage in SCOPED_AUTHORITY_TCK_FAILURE_STAGES_V2
    ),
    *(f"state_store:tamper:{case}" for case in GOVERNANCE_STATE_STORE_TAMPER_CASES_V2),
)

_AUTHORITY_PROFILES_V2 = (
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
)
_ARTIFACT_FIELDS = frozenset(
    {
        "tck_version",
        "state_store_conformance_version",
        "authority_session_conformance_version",
        "baseline_output_conformance_version",
        "cases",
    }
)
_REQUEST_FIELDS = frozenset(
    {"tck_version", "case_id", "operation", "profile", "payload"}
)
_CASE_FIELDS = frozenset(
    {
        "id",
        "operation",
        "profile",
        "request",
        "required_invariants",
        "failure_stage",
    }
)
_CASE_REPORT_FIELDS = frozenset(
    {
        "id",
        "ok",
        "observed_invariants",
        "diagnostic_code",
        "failure_stage",
        "detail",
    }
)
_REPORT_FIELDS = frozenset(
    {
        "tck_version",
        "state_store_conformance_version",
        "authority_session_conformance_version",
        "baseline_output_conformance_version",
        "implementation_id",
        "results",
    }
)


class ScopedAuthorityTckArtifactCodeV2(StrEnum):
    """Closed errors for malformed or incompatible TCK artifacts."""

    INVALID_JSON = "scoped_authority_tck_invalid_json"
    INVALID_FIELDS = "scoped_authority_tck_invalid_fields"
    INVALID_VERSION = "scoped_authority_tck_invalid_version"
    INVALID_VALUE = "scoped_authority_tck_invalid_value"


class ScopedAuthorityTckArtifactErrorV2(ValueError):
    """Typed reader error; it is diagnostic data, never authority."""

    __slots__ = ("code", "path", "detail")

    def __init__(
        self,
        code: ScopedAuthorityTckArtifactCodeV2,
        path: str,
        detail: str,
    ) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code.value}:{path}:{detail}")


@dataclass(frozen=True, slots=True)
class ScopedAuthorityTckRequestV2:
    """One expected-free subject request carrying an existing authority wire."""

    case_id: str
    operation: str
    profile: str
    payload: AuthorityWireRecordV2
    tck_version: str = SCOPED_AUTHORITY_TCK_VERSION_V2

    def __post_init__(self) -> None:
        _require_version(self.tck_version, "/request/tck_version")
        _require_case_id(self.case_id, "/request/case_id")
        _require_member(
            self.operation,
            SCOPED_AUTHORITY_TCK_OPERATIONS_V2,
            "/request/operation",
        )
        _require_member(self.profile, _AUTHORITY_PROFILES_V2, "/request/profile")
        try:
            snapshot = read_authority_wire_record_v2(self.payload.to_dict())
        except (AttributeError, AuthorityWireValidationErrorV2) as exc:
            raise ScopedAuthorityTckArtifactErrorV2(
                ScopedAuthorityTckArtifactCodeV2.INVALID_VALUE,
                "/request/payload",
                "request payload must be one canonical authority-v2 wire record",
            ) from exc
        object.__setattr__(self, "payload", snapshot)

    def to_dict(self) -> dict[str, object]:
        return {
            "tck_version": self.tck_version,
            "case_id": self.case_id,
            "operation": self.operation,
            "profile": self.profile,
            "payload": self.payload.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: object) -> ScopedAuthorityTckRequestV2:
        value = _exact_object(payload, _REQUEST_FIELDS, "/request")
        try:
            record = read_authority_wire_record_v2(value["payload"])
        except AuthorityWireValidationErrorV2 as exc:
            raise ScopedAuthorityTckArtifactErrorV2(
                ScopedAuthorityTckArtifactCodeV2.INVALID_VALUE,
                "/request/payload",
                exc.detail,
            ) from exc
        return cls(
            tck_version=value["tck_version"],
            case_id=value["case_id"],
            operation=value["operation"],
            profile=value["profile"],
            payload=record,
        )


@dataclass(frozen=True, slots=True)
class ScopedAuthorityTckCaseV2:
    """Harness-owned case metadata around one expected-free request."""

    id: str
    operation: str
    profile: str
    request: ScopedAuthorityTckRequestV2
    required_invariants: tuple[str, ...]
    failure_stage: str | None = None

    def __post_init__(self) -> None:
        _require_case_id(self.id, "/case/id")
        _require_member(
            self.operation,
            SCOPED_AUTHORITY_TCK_OPERATIONS_V2,
            "/case/operation",
        )
        _require_member(self.profile, _AUTHORITY_PROFILES_V2, "/case/profile")
        if type(self.request) is not ScopedAuthorityTckRequestV2:
            _invalid("/case/request", "case request must use the exact TCK type")
        if (self.id, self.operation, self.profile) != (
            self.request.case_id,
            self.request.operation,
            self.request.profile,
        ):
            _invalid("/case/request", "case and request bindings must be exact")
        _require_invariants(self.required_invariants, "/case/required_invariants")
        _require_failure_stage(self.failure_stage, "/case/failure_stage")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "operation": self.operation,
            "profile": self.profile,
            "request": self.request.to_dict(),
            "required_invariants": list(self.required_invariants),
            "failure_stage": self.failure_stage,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ScopedAuthorityTckCaseV2:
        value = _exact_object(payload, _CASE_FIELDS, "/case")
        return cls(
            id=value["id"],
            operation=value["operation"],
            profile=value["profile"],
            request=ScopedAuthorityTckRequestV2.from_dict(value["request"]),
            required_invariants=_string_tuple(
                value["required_invariants"],
                "/case/required_invariants",
            ),
            failure_stage=value["failure_stage"],
        )


@dataclass(frozen=True, slots=True)
class ScopedAuthorityTckCaseReportV2:
    """Actual observed case facts; no expected outcome is serialized here."""

    id: str
    ok: bool
    observed_invariants: tuple[str, ...]
    diagnostic_code: AuthorityDiagnosticCodeV2 | None
    failure_stage: str | None
    detail: str

    def __post_init__(self) -> None:
        _require_case_id(self.id, "/result/id")
        if type(self.ok) is not bool:
            _invalid("/result/ok", "case result ok must be an exact boolean")
        _require_invariants(
            self.observed_invariants,
            "/result/observed_invariants",
            allow_empty=True,
        )
        if self.diagnostic_code is not None and (
            type(self.diagnostic_code) is not AuthorityDiagnosticCodeV2
        ):
            _invalid(
                "/result/diagnostic_code",
                "diagnostic_code must use the Protocol-owned closed enum",
            )
        _require_failure_stage(self.failure_stage, "/result/failure_stage")
        _require_portable_text(
            self.detail,
            "/result/detail",
            allow_empty=True,
            require_trimmed=False,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "ok": self.ok,
            "observed_invariants": list(self.observed_invariants),
            "diagnostic_code": (
                None if self.diagnostic_code is None else self.diagnostic_code.value
            ),
            "failure_stage": self.failure_stage,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ScopedAuthorityTckCaseReportV2:
        value = _exact_object(payload, _CASE_REPORT_FIELDS, "/result")
        diagnostic = value["diagnostic_code"]
        if diagnostic is not None:
            try:
                diagnostic = AuthorityDiagnosticCodeV2(diagnostic)
            except (TypeError, ValueError) as exc:
                raise ScopedAuthorityTckArtifactErrorV2(
                    ScopedAuthorityTckArtifactCodeV2.INVALID_VALUE,
                    "/result/diagnostic_code",
                    "diagnostic_code is unsupported",
                ) from exc
        return cls(
            id=value["id"],
            ok=value["ok"],
            observed_invariants=_string_tuple(
                value["observed_invariants"],
                "/result/observed_invariants",
            ),
            diagnostic_code=diagnostic,
            failure_stage=value["failure_stage"],
            detail=value["detail"],
        )


@dataclass(frozen=True, slots=True)
class ScopedAuthorityTckArtifactV2:
    """Complete canonical case catalog for all three active authority matrices."""

    cases: tuple[ScopedAuthorityTckCaseV2, ...]
    tck_version: str = SCOPED_AUTHORITY_TCK_VERSION_V2
    state_store_conformance_version: str = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2
    authority_session_conformance_version: str = (
        GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2
    )
    baseline_output_conformance_version: str = (
        GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2
    )

    def __post_init__(self) -> None:
        _require_common_versions(self)
        if type(self.cases) is not tuple or any(
            type(item) is not ScopedAuthorityTckCaseV2 for item in self.cases
        ):
            _invalid("/cases", "TCK cases must use exact immutable case records")
        ids = tuple(item.id for item in self.cases)
        if ids != SCOPED_AUTHORITY_TCK_CASE_IDS_V2:
            _invalid(
                "/cases",
                "TCK artifact must contain every declared case exactly once in order",
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "tck_version": self.tck_version,
            "state_store_conformance_version": (self.state_store_conformance_version),
            "authority_session_conformance_version": (
                self.authority_session_conformance_version
            ),
            "baseline_output_conformance_version": (
                self.baseline_output_conformance_version
            ),
            "cases": [item.to_dict() for item in self.cases],
        }

    @classmethod
    def from_dict(cls, payload: object) -> ScopedAuthorityTckArtifactV2:
        value = _exact_object(payload, _ARTIFACT_FIELDS, "")
        cases = value["cases"]
        if type(cases) is not list:
            _invalid("/cases", "TCK cases must be an array")
        return cls(
            tck_version=value["tck_version"],
            state_store_conformance_version=value["state_store_conformance_version"],
            authority_session_conformance_version=value[
                "authority_session_conformance_version"
            ],
            baseline_output_conformance_version=value[
                "baseline_output_conformance_version"
            ],
            cases=tuple(ScopedAuthorityTckCaseV2.from_dict(item) for item in cases),
        )


@dataclass(frozen=True, slots=True)
class ScopedAuthorityTckReportV2:
    """Complete actual-only report; expected invariants remain harness-owned."""

    implementation_id: str
    results: tuple[ScopedAuthorityTckCaseReportV2, ...]
    tck_version: str = SCOPED_AUTHORITY_TCK_VERSION_V2
    state_store_conformance_version: str = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2
    authority_session_conformance_version: str = (
        GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2
    )
    baseline_output_conformance_version: str = (
        GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2
    )

    def __post_init__(self) -> None:
        _require_common_versions(self)
        _require_portable_text(self.implementation_id, "/implementation_id")
        if type(self.results) is not tuple or any(
            type(item) is not ScopedAuthorityTckCaseReportV2 for item in self.results
        ):
            _invalid("/results", "TCK results must use exact immutable records")
        ids = tuple(item.id for item in self.results)
        if ids != SCOPED_AUTHORITY_TCK_CASE_IDS_V2:
            _invalid(
                "/results",
                "TCK report must contain every declared case exactly once in order",
            )

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(item.ok for item in self.results)

    def to_dict(self) -> dict[str, object]:
        return {
            "tck_version": self.tck_version,
            "state_store_conformance_version": (self.state_store_conformance_version),
            "authority_session_conformance_version": (
                self.authority_session_conformance_version
            ),
            "baseline_output_conformance_version": (
                self.baseline_output_conformance_version
            ),
            "implementation_id": self.implementation_id,
            "results": [item.to_dict() for item in self.results],
        }

    @classmethod
    def from_dict(cls, payload: object) -> ScopedAuthorityTckReportV2:
        value = _exact_object(payload, _REPORT_FIELDS, "")
        results = value["results"]
        if type(results) is not list:
            _invalid("/results", "TCK results must be an array")
        return cls(
            tck_version=value["tck_version"],
            state_store_conformance_version=value["state_store_conformance_version"],
            authority_session_conformance_version=value[
                "authority_session_conformance_version"
            ],
            baseline_output_conformance_version=value[
                "baseline_output_conformance_version"
            ],
            implementation_id=value["implementation_id"],
            results=tuple(
                ScopedAuthorityTckCaseReportV2.from_dict(item) for item in results
            ),
        )


ScopedAuthorityTckDocumentV2: TypeAlias = (
    ScopedAuthorityTckArtifactV2 | ScopedAuthorityTckReportV2
)


def read_scoped_authority_tck_document_v2(
    payload: object,
) -> ScopedAuthorityTckDocumentV2:
    """Dispatch one exact case artifact or actual-only report by closed fields."""

    if type(payload) is not dict:
        _invalid("", "scoped-authority TCK document must be an exact object")
    fields = frozenset(cast(dict[str, Any], payload))
    if fields == _ARTIFACT_FIELDS:
        return ScopedAuthorityTckArtifactV2.from_dict(payload)
    if fields == _REPORT_FIELDS:
        return ScopedAuthorityTckReportV2.from_dict(payload)
    raise ScopedAuthorityTckArtifactErrorV2(
        ScopedAuthorityTckArtifactCodeV2.INVALID_FIELDS,
        "",
        "scoped-authority TCK document fields are not a declared artifact shape",
    )


def loads_scoped_authority_tck_document_v2(
    value: str | bytes | bytearray,
) -> ScopedAuthorityTckDocumentV2:
    """Strictly decode one UTF-8 TCK artifact/report JSON document."""

    text = _require_json_text(value)
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_number,
        )
    except ScopedAuthorityTckArtifactErrorV2:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ScopedAuthorityTckArtifactErrorV2(
            ScopedAuthorityTckArtifactCodeV2.INVALID_JSON,
            "",
            "scoped-authority TCK JSON is invalid",
        ) from exc
    return read_scoped_authority_tck_document_v2(payload)


def validate_scoped_authority_tck_document_v2(payload: object) -> None:
    """Validate one artifact/report with the exact typed-reader semantics."""

    read_scoped_authority_tck_document_v2(payload)


def scoped_authority_tck_v2_schema() -> dict[str, Any]:
    """Return the Draft case-artifact/report schema with expected-free requests."""

    request = _closed(
        {
            "tck_version": {"const": SCOPED_AUTHORITY_TCK_VERSION_V2},
            "case_id": {"enum": list(SCOPED_AUTHORITY_TCK_CASE_IDS_V2)},
            "operation": {"enum": list(SCOPED_AUTHORITY_TCK_OPERATIONS_V2)},
            "profile": {"enum": list(_AUTHORITY_PROFILES_V2)},
            "payload": {"$ref": AUTHORITY_SCHEMA_V2_ID},
        }
    )
    invariant_array = {
        "type": "array",
        "uniqueItems": True,
        "items": {"enum": list(SCOPED_AUTHORITY_TCK_INVARIANTS_V2)},
    }
    failure_stage = {
        "oneOf": [
            {"type": "null"},
            {"enum": list(SCOPED_AUTHORITY_TCK_FAILURE_STAGES_V2)},
        ]
    }
    case = {
        **_closed(
            {
                "id": {"enum": list(SCOPED_AUTHORITY_TCK_CASE_IDS_V2)},
                "operation": {"enum": list(SCOPED_AUTHORITY_TCK_OPERATIONS_V2)},
                "profile": {"enum": list(_AUTHORITY_PROFILES_V2)},
                "request": {"$ref": "#/$defs/request"},
                "required_invariants": {**invariant_array, "minItems": 1},
                "failure_stage": failure_stage,
            }
        ),
        "allOf": [
            _same_case_request_binding(
                "id",
                "case_id",
                SCOPED_AUTHORITY_TCK_CASE_IDS_V2,
            ),
            _same_case_request_binding(
                "operation",
                "operation",
                SCOPED_AUTHORITY_TCK_OPERATIONS_V2,
            ),
            _same_case_request_binding(
                "profile",
                "profile",
                _AUTHORITY_PROFILES_V2,
            ),
        ],
    }
    case_report = _closed(
        {
            "id": {"enum": list(SCOPED_AUTHORITY_TCK_CASE_IDS_V2)},
            "ok": {"type": "boolean"},
            "observed_invariants": invariant_array,
            "diagnostic_code": {
                "oneOf": [
                    {"type": "null"},
                    {"enum": [item.value for item in AuthorityDiagnosticCodeV2]},
                ]
            },
            "failure_stage": failure_stage,
            "detail": {"type": "string"},
        }
    )
    common = {
        "tck_version": {"const": SCOPED_AUTHORITY_TCK_VERSION_V2},
        "state_store_conformance_version": {
            "const": GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2
        },
        "authority_session_conformance_version": {
            "const": GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2
        },
        "baseline_output_conformance_version": {
            "const": GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2
        },
    }
    artifact = _closed(
        {
            **common,
            "cases": _ordered_case_array("#/$defs/case"),
        }
    )
    report = _closed(
        {
            **common,
            "implementation_id": {"type": "string", "minLength": 1},
            "results": _ordered_case_array("#/$defs/caseReport"),
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCOPED_AUTHORITY_TCK_SCHEMA_V2_ID,
        "title": "PheroOS Draft scoped-authority v2 TCK artifact or report",
        "oneOf": [
            {"$ref": "#/$defs/artifact"},
            {"$ref": "#/$defs/report"},
        ],
        "$defs": {
            "request": request,
            "case": case,
            "caseReport": case_report,
            "artifact": artifact,
            "report": report,
        },
    }


def _require_common_versions(value: object) -> None:
    _require_version(getattr(value, "tck_version"), "/tck_version")
    versions = (
        (
            getattr(value, "state_store_conformance_version"),
            GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
            "/state_store_conformance_version",
        ),
        (
            getattr(value, "authority_session_conformance_version"),
            GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2,
            "/authority_session_conformance_version",
        ),
        (
            getattr(value, "baseline_output_conformance_version"),
            GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2,
            "/baseline_output_conformance_version",
        ),
    )
    for observed, expected, path in versions:
        if type(observed) is not str or observed != expected:
            raise ScopedAuthorityTckArtifactErrorV2(
                ScopedAuthorityTckArtifactCodeV2.INVALID_VERSION,
                path,
                "Conformance contract version is unsupported",
            )


def _require_version(value: object, path: str) -> None:
    if type(value) is not str or value != SCOPED_AUTHORITY_TCK_VERSION_V2:
        raise ScopedAuthorityTckArtifactErrorV2(
            ScopedAuthorityTckArtifactCodeV2.INVALID_VERSION,
            path,
            "scoped-authority TCK version is unsupported",
        )


def _require_case_id(value: object, path: str) -> None:
    _require_member(value, SCOPED_AUTHORITY_TCK_CASE_IDS_V2, path)


def _require_member(value: object, registry: tuple[str, ...], path: str) -> None:
    if type(value) is not str or value not in registry:
        _invalid(path, "value is outside the closed TCK registry")


def _require_invariants(
    value: object,
    path: str,
    *,
    allow_empty: bool = False,
) -> None:
    if type(value) is not tuple:
        _invalid(path, "invariants must be an exact immutable tuple")
    typed = cast(tuple[object, ...], value)
    if (not allow_empty and not typed) or any(
        type(item) is not str or item not in SCOPED_AUTHORITY_TCK_INVARIANTS_V2
        for item in typed
    ):
        _invalid(path, "invariants contain an undeclared label")
    canonical = tuple(
        item for item in SCOPED_AUTHORITY_TCK_INVARIANTS_V2 if item in typed
    )
    if len(typed) != len(set(typed)) or typed != canonical:
        _invalid(path, "invariants must be unique and use registry order")


def _require_failure_stage(value: object, path: str) -> None:
    if value is not None and (
        type(value) is not str or value not in SCOPED_AUTHORITY_TCK_FAILURE_STAGES_V2
    ):
        _invalid(path, "failure_stage is outside the StateStore TCK registry")


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        _invalid(path, "value must be an exact string array")
    return tuple(cast(list[str], value))


def _require_portable_text(
    value: object,
    path: str,
    *,
    allow_empty: bool = False,
    require_trimmed: bool = True,
) -> str:
    if (
        type(value) is not str
        or (not allow_empty and not value)
        or (require_trimmed and value and value != value.strip())
        or unicodedata.normalize("NFC", value) != value
        or "\x00" in value
    ):
        _invalid(path, "value must be canonical NFC text without U+0000")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ScopedAuthorityTckArtifactErrorV2(
            ScopedAuthorityTckArtifactCodeV2.INVALID_VALUE,
            path,
            "value must encode as UTF-8",
        ) from exc
    return value


def _require_json_text(value: object) -> str:
    if type(value) is str:
        text = value
    elif isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ScopedAuthorityTckArtifactErrorV2(
                ScopedAuthorityTckArtifactCodeV2.INVALID_JSON,
                "",
                "scoped-authority TCK JSON must not use a BOM",
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ScopedAuthorityTckArtifactErrorV2(
                ScopedAuthorityTckArtifactCodeV2.INVALID_JSON,
                "",
                "scoped-authority TCK JSON must use UTF-8",
            ) from exc
    else:
        raise ScopedAuthorityTckArtifactErrorV2(
            ScopedAuthorityTckArtifactCodeV2.INVALID_JSON,
            "",
            "scoped-authority TCK JSON must be text, bytes, or bytearray",
        )
    if text.startswith("\ufeff"):
        raise ScopedAuthorityTckArtifactErrorV2(
            ScopedAuthorityTckArtifactCodeV2.INVALID_JSON,
            "",
            "scoped-authority TCK JSON must not use a BOM",
        )
    return text


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if unicodedata.normalize("NFC", key) != key:
            raise ScopedAuthorityTckArtifactErrorV2(
                ScopedAuthorityTckArtifactCodeV2.INVALID_JSON,
                "",
                "scoped-authority TCK object keys must already use NFC",
            )
        if key in value:
            raise ScopedAuthorityTckArtifactErrorV2(
                ScopedAuthorityTckArtifactCodeV2.INVALID_JSON,
                f"/{key}",
                "scoped-authority TCK JSON contains a duplicate object key",
            )
        value[key] = item
    return value


def _reject_nonfinite_number(value: str) -> NoReturn:
    raise ScopedAuthorityTckArtifactErrorV2(
        ScopedAuthorityTckArtifactCodeV2.INVALID_JSON,
        "",
        f"scoped-authority TCK JSON does not permit {value}",
    )


def _exact_object(
    payload: object,
    fields: frozenset[str],
    path: str,
) -> dict[str, Any]:
    if type(payload) is not dict:
        raise ScopedAuthorityTckArtifactErrorV2(
            ScopedAuthorityTckArtifactCodeV2.INVALID_FIELDS,
            path,
            "value must be an exact JSON object",
        )
    if set(payload) != fields:
        raise ScopedAuthorityTckArtifactErrorV2(
            ScopedAuthorityTckArtifactCodeV2.INVALID_FIELDS,
            path,
            "object fields are not the declared closed shape",
        )
    return payload


def _invalid(path: str, detail: str) -> NoReturn:
    raise ScopedAuthorityTckArtifactErrorV2(
        ScopedAuthorityTckArtifactCodeV2.INVALID_VALUE,
        path,
        detail,
    )


def _closed(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(properties),
        "properties": properties,
        "additionalProperties": False,
    }


def _same_case_request_binding(
    case_field: str,
    request_field: str,
    registry: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "oneOf": [
            {
                "properties": {
                    case_field: {"const": value},
                    "request": {
                        "properties": {request_field: {"const": value}},
                    },
                },
            }
            for value in registry
        ]
    }


def _ordered_case_array(item_ref: str) -> dict[str, Any]:
    return {
        "type": "array",
        "minItems": len(SCOPED_AUTHORITY_TCK_CASE_IDS_V2),
        "maxItems": len(SCOPED_AUTHORITY_TCK_CASE_IDS_V2),
        "prefixItems": [
            {
                "allOf": [
                    {"$ref": item_ref},
                    {"properties": {"id": {"const": case_id}}},
                ]
            }
            for case_id in SCOPED_AUTHORITY_TCK_CASE_IDS_V2
        ],
        "items": False,
    }


__all__ = [
    "AUTHORITY_SESSION_TCK_CASE_IDS_V2",
    "BASELINE_OUTPUT_TCK_CASE_IDS_V2",
    "SCOPED_AUTHORITY_TCK_CASE_IDS_V2",
    "SCOPED_AUTHORITY_TCK_FAILURE_STAGES_V2",
    "SCOPED_AUTHORITY_TCK_INVARIANTS_V2",
    "SCOPED_AUTHORITY_TCK_OPERATIONS_V2",
    "SCOPED_AUTHORITY_TCK_SCHEMA_V2",
    "SCOPED_AUTHORITY_TCK_SCHEMA_V2_ID",
    "SCOPED_AUTHORITY_TCK_VERSION_V2",
    "STATE_STORE_TCK_CASE_IDS_V2",
    "ScopedAuthorityTckArtifactCodeV2",
    "ScopedAuthorityTckArtifactErrorV2",
    "ScopedAuthorityTckArtifactV2",
    "ScopedAuthorityTckCaseReportV2",
    "ScopedAuthorityTckCaseV2",
    "ScopedAuthorityTckDocumentV2",
    "ScopedAuthorityTckReportV2",
    "ScopedAuthorityTckRequestV2",
    "loads_scoped_authority_tck_document_v2",
    "read_scoped_authority_tck_document_v2",
    "scoped_authority_tck_v2_schema",
    "validate_scoped_authority_tck_document_v2",
]
