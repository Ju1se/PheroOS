"""Closed expected-free records for Runtime Integration transcript v1."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pheroos.conformance._runtime_compatibility_contracts import (
    RuntimeCompatibilityClaimV1,
)
from pheroos.drivers import (
    DriverInvocationReceiptV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerGrantV2,
    GovernanceVerifiedSignalRequestV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceStateReaderV2,
)
from pheroos.governance.baseline_output_v2 import (
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
)
from pheroos.governance.commit_decision_v2 import CommitDecisionOutcomeV2
from pheroos.governance.commit_finality_v2 import (
    CommitFinalityProjectionV2,
)
from pheroos.governance.commit_certificate_v2 import (
    VerifiedCommitCertificateStateV2,
)
from pheroos.kernel import RuntimeScope
from pheroos.protocol import ScopedCapabilityManifestV2
from pheroos.trace import ScopedTraceCheckpointV2

from pheroos.conformance._runtime_integration_codec import (
    RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1,
    RUNTIME_INTEGRATION_CONTROL_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1,
    RuntimeIntegrationTranscriptErrorV1,
    canonical_bytes,
    document_root,
    exact_mapping,
    root_value,
    text_value,
)


class RuntimeTranscriptDispositionV1(StrEnum):
    COMPLETED = "completed"
    RUNTIME_TIMED_OUT = "runtime_timed_out"
    RUNTIME_CANCELLED = "runtime_cancelled"


@dataclass(frozen=True, slots=True)
class RuntimeCommitObservationV1:
    """Portable Commit v2 input data; never a current authority handle.

    The stale-certificate lane carries two exact finality projections from one
    owner stream.  Their successor relationship is an observation for the TCK;
    neither projection grants publication or execution authority.
    """

    outcome: CommitDecisionOutcomeV2
    observed_finality: CommitFinalityProjectionV2 | None = None
    successor_finality: CommitFinalityProjectionV2 | None = None
    version: str = RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1

    def __post_init__(self) -> None:
        if self.version != RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime Commit observation version is unsupported"
            )
        if type(self.outcome) is not CommitDecisionOutcomeV2:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime Commit observation outcome is noncanonical"
            )
        for projection in (self.observed_finality, self.successor_finality):
            if (
                projection is not None
                and type(projection) is not CommitFinalityProjectionV2
            ):
                raise RuntimeIntegrationTranscriptErrorV1(
                    "runtime Commit finality projection is noncanonical"
                )
        from pheroos.conformance._runtime_integration_validation import (
            validate_commit_observation_v1,
        )

        validate_commit_observation_v1(self)
        canonical_bytes(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "outcome": self.outcome.to_dict(),
            "observed_finality": (
                None
                if self.observed_finality is None
                else self.observed_finality.to_dict()
            ),
            "successor_finality": (
                None
                if self.successor_finality is None
                else self.successor_finality.to_dict()
            ),
        }

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeCommitObservationV1:
        value = exact_mapping(
            payload,
            set(_COMMIT_OBSERVATION_FIELDS),
            "runtime Commit observation",
        )
        return cls(
            version=value["version"],
            outcome=CommitDecisionOutcomeV2.from_dict(value["outcome"]),
            observed_finality=_optional_finality(value["observed_finality"]),
            successor_finality=_optional_finality(value["successor_finality"]),
        )


@dataclass(frozen=True, slots=True)
class RuntimeControlInputV1:
    """Non-authoritative outer-runtime observations and negative action gates."""

    wall_clock_timed_out: bool = False
    cancel_requested: bool = False
    repeat_invocation: bool = False
    recover_after_commit: bool = False
    supersede_before_recovery: bool = False
    advance_permission_before_recovery: bool = False
    advance_stop_before_recovery: bool = False
    omit_permission: bool = False
    inject_cas_conflict: bool = False
    version: str = RUNTIME_INTEGRATION_CONTROL_VERSION_V1

    def __post_init__(self) -> None:
        if self.version != RUNTIME_INTEGRATION_CONTROL_VERSION_V1:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime control version is unsupported"
            )
        for name in (
            "wall_clock_timed_out",
            "cancel_requested",
            "repeat_invocation",
            "recover_after_commit",
            "supersede_before_recovery",
            "advance_permission_before_recovery",
            "advance_stop_before_recovery",
            "omit_permission",
            "inject_cas_conflict",
        ):
            if type(getattr(self, name)) is not bool:
                raise RuntimeIntegrationTranscriptErrorV1(
                    f"runtime control {name} must be boolean"
                )
        if self.supersede_before_recovery and not self.recover_after_commit:
            raise RuntimeIntegrationTranscriptErrorV1(
                "supersession requires crash recovery observation"
            )
        if (
            self.advance_permission_before_recovery or self.advance_stop_before_recovery
        ) and not self.recover_after_commit:
            raise RuntimeIntegrationTranscriptErrorV1(
                "dependency advancement requires crash recovery observation"
            )
        if (
            self.advance_permission_before_recovery
            and self.advance_stop_before_recovery
        ):
            raise RuntimeIntegrationTranscriptErrorV1(
                "one recovery case may advance only one dependency"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "wall_clock_timed_out": self.wall_clock_timed_out,
            "cancel_requested": self.cancel_requested,
            "repeat_invocation": self.repeat_invocation,
            "recover_after_commit": self.recover_after_commit,
            "supersede_before_recovery": self.supersede_before_recovery,
            "advance_permission_before_recovery": self.advance_permission_before_recovery,
            "advance_stop_before_recovery": self.advance_stop_before_recovery,
            "omit_permission": self.omit_permission,
            "inject_cas_conflict": self.inject_cas_conflict,
        }

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeControlInputV1:
        value = exact_mapping(payload, set(_CONTROL_FIELDS), "runtime control")
        return cls(**value)


@dataclass(frozen=True, slots=True)
class RuntimeTranscriptStepV1:
    sequence: int
    layer: str
    artifact_version: str
    artifact_root: str
    predecessor_root: str
    version: str = RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1
    step_root: str = ""

    def __post_init__(self) -> None:
        if self.version != RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript step version is unsupported"
            )
        if type(self.sequence) is not int or self.sequence < 0:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript step sequence is invalid"
            )
        text_value(self.layer, "runtime transcript step layer")
        text_value(self.artifact_version, "runtime transcript artifact version")
        root_value(self.artifact_root, "runtime transcript artifact root")
        root_value(
            self.predecessor_root,
            "runtime transcript predecessor root",
            allow_empty=True,
        )
        computed = document_root("step", self._body())
        if self.step_root and self.step_root != computed:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript step root is mismatched"
            )
        object.__setattr__(self, "step_root", computed)

    def _body(self) -> dict[str, object]:
        return {
            "version": self.version,
            "sequence": self.sequence,
            "layer": self.layer,
            "artifact_version": self.artifact_version,
            "artifact_root": self.artifact_root,
            "predecessor_root": self.predecessor_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "step_root": self.step_root}

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeTranscriptStepV1:
        value = exact_mapping(payload, set(_STEP_FIELDS), "runtime transcript step")
        return cls(**value)


@dataclass(frozen=True, slots=True)
class RuntimeTranscriptRequestV1:
    """Preconstructed input facts; deliberately contains no expected result."""

    scenario_id: str
    scope: RuntimeScope
    compatibility_claim: RuntimeCompatibilityClaimV1
    capability: ScopedCapabilityManifestV2
    authority_domain: AuthorityDomainV2
    issuer_grant: GovernanceIssuerGrantV2
    driver_request: DriverInvocationRequestV2
    driver_result: DriverInvocationResultV2
    verified_signal_requests: tuple[GovernanceVerifiedSignalRequestV2, ...]
    baseline_request: BaselineOutputRequestV2 | None
    commit_observation: RuntimeCommitObservationV1 | None
    control: RuntimeControlInputV1
    successor_request: BaselineOutputRequestV2 | None = None
    contender_request: BaselineOutputRequestV2 | None = None
    version: str = RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1
    request_root: str = ""

    def __post_init__(self) -> None:
        from pheroos.conformance._runtime_integration_validation import (
            validate_transcript_request_v1,
        )

        validate_transcript_request_v1(self)
        computed = document_root("request", self._body())
        if self.request_root and self.request_root != computed:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript request root is mismatched"
            )
        object.__setattr__(self, "request_root", computed)
        canonical_bytes(self.to_dict())

    def _body(self) -> dict[str, object]:
        return {
            "version": self.version,
            "scenario_id": self.scenario_id,
            "scope": self.scope.to_dict(),
            "compatibility_claim": self.compatibility_claim.to_dict(),
            "capability": self.capability.to_dict(),
            "authority_domain": self.authority_domain.to_dict(),
            "issuer_grant": self.issuer_grant.to_dict(),
            "driver_request": self.driver_request.to_dict(),
            "driver_result": self.driver_result.to_dict(),
            "verified_signal_requests": [
                item.to_dict() for item in self.verified_signal_requests
            ],
            "baseline_request": (
                None
                if self.baseline_request is None
                else self.baseline_request.to_dict()
            ),
            "commit_observation": (
                None
                if self.commit_observation is None
                else self.commit_observation.to_dict()
            ),
            "control": self.control.to_dict(),
            "successor_request": (
                None
                if self.successor_request is None
                else self.successor_request.to_dict()
            ),
            "contender_request": (
                None
                if self.contender_request is None
                else self.contender_request.to_dict()
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeTranscriptRequestV1:
        value = exact_mapping(
            payload, set(_REQUEST_FIELDS), "runtime transcript request"
        )
        signals = value["verified_signal_requests"]
        if type(signals) is not list:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript verified signals must be an array"
            )
        return cls(
            scenario_id=value["scenario_id"],
            scope=RuntimeScope.from_dict(value["scope"]),
            compatibility_claim=RuntimeCompatibilityClaimV1.from_dict(
                value["compatibility_claim"]
            ),
            capability=ScopedCapabilityManifestV2.from_dict(value["capability"]),
            authority_domain=AuthorityDomainV2.from_dict(value["authority_domain"]),
            issuer_grant=GovernanceIssuerGrantV2.from_dict(value["issuer_grant"]),
            driver_request=DriverInvocationRequestV2.from_dict(value["driver_request"]),
            driver_result=DriverInvocationResultV2.from_dict(value["driver_result"]),
            verified_signal_requests=tuple(
                GovernanceVerifiedSignalRequestV2.from_dict(item) for item in signals
            ),
            baseline_request=_optional_baseline_request(value["baseline_request"]),
            commit_observation=_optional_commit_observation(
                value["commit_observation"]
            ),
            control=RuntimeControlInputV1.from_dict(value["control"]),
            successor_request=_optional_baseline_request(value["successor_request"]),
            contender_request=_optional_baseline_request(value["contender_request"]),
            version=value["version"],
            request_root=value["request_root"],
        )


@dataclass(frozen=True, slots=True)
class RuntimeTranscriptResultV1:
    implementation_id: str
    request_root: str
    disposition: RuntimeTranscriptDispositionV1
    compatibility_manifest_root: str
    compatibility_report_version: str
    compatibility_ok: bool
    plan_document: Mapping[str, Any]
    plan_root: str
    driver_receipts: tuple[DriverInvocationReceiptV2, ...]
    driver_restarted_receipt: DriverInvocationReceiptV2
    driver_checkpoint_wire: str
    driver_checkpoint_root: str
    governance_result: BaselineOutputResultV2 | None
    commit_outcome: CommitDecisionOutcomeV2 | None
    trace_checkpoint: ScopedTraceCheckpointV2
    delivery_eligible: bool
    publication_authorized: bool
    execution_authorized: bool
    recovered_after_commit: bool
    diagnostics: tuple[str, ...]
    steps: tuple[RuntimeTranscriptStepV1, ...]
    version: str = RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1
    result_root: str = ""

    def __post_init__(self) -> None:
        from pheroos.conformance._runtime_integration_validation import (
            validate_transcript_result_v1,
        )

        validate_transcript_result_v1(self)
        object.__setattr__(self, "plan_document", deepcopy(dict(self.plan_document)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        computed = document_root("result", self._body())
        if self.result_root and self.result_root != computed:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript result root is mismatched"
            )
        object.__setattr__(self, "result_root", computed)
        canonical_bytes(self.to_dict())

    def _body(self) -> dict[str, object]:
        return {
            "version": self.version,
            "implementation_id": self.implementation_id,
            "request_root": self.request_root,
            "disposition": self.disposition.value,
            "compatibility_manifest_root": self.compatibility_manifest_root,
            "compatibility_report_version": self.compatibility_report_version,
            "compatibility_ok": self.compatibility_ok,
            "plan_document": deepcopy(dict(self.plan_document)),
            "plan_root": self.plan_root,
            "driver_receipts": [item.to_dict() for item in self.driver_receipts],
            "driver_restarted_receipt": self.driver_restarted_receipt.to_dict(),
            "driver_checkpoint_wire": self.driver_checkpoint_wire,
            "driver_checkpoint_root": self.driver_checkpoint_root,
            "governance_result": (
                None
                if self.governance_result is None
                else self.governance_result.to_dict()
            ),
            "commit_outcome": (
                None if self.commit_outcome is None else self.commit_outcome.to_dict()
            ),
            "trace_checkpoint": self.trace_checkpoint.to_dict(),
            "delivery_eligible": self.delivery_eligible,
            "publication_authorized": self.publication_authorized,
            "execution_authorized": self.execution_authorized,
            "recovered_after_commit": self.recovered_after_commit,
            "diagnostics": list(self.diagnostics),
            "steps": [item.to_dict() for item in self.steps],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "result_root": self.result_root}

    @classmethod
    def from_dict(cls, payload: object) -> RuntimeTranscriptResultV1:
        value = exact_mapping(payload, set(_RESULT_FIELDS), "runtime transcript result")
        receipts = value["driver_receipts"]
        diagnostics = value["diagnostics"]
        steps = value["steps"]
        if not all(type(item) is list for item in (receipts, diagnostics, steps)):
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript result collections must be arrays"
            )
        return cls(
            implementation_id=value["implementation_id"],
            request_root=value["request_root"],
            disposition=RuntimeTranscriptDispositionV1(value["disposition"]),
            compatibility_manifest_root=value["compatibility_manifest_root"],
            compatibility_report_version=value["compatibility_report_version"],
            compatibility_ok=value["compatibility_ok"],
            plan_document=value["plan_document"],
            plan_root=value["plan_root"],
            driver_receipts=tuple(
                DriverInvocationReceiptV2.from_dict(item) for item in receipts
            ),
            driver_restarted_receipt=DriverInvocationReceiptV2.from_dict(
                value["driver_restarted_receipt"]
            ),
            driver_checkpoint_wire=value["driver_checkpoint_wire"],
            driver_checkpoint_root=value["driver_checkpoint_root"],
            governance_result=_optional_baseline_result(value["governance_result"]),
            commit_outcome=_optional_commit_outcome(value["commit_outcome"]),
            trace_checkpoint=ScopedTraceCheckpointV2.from_dict(
                value["trace_checkpoint"]
            ),
            delivery_eligible=value["delivery_eligible"],
            publication_authorized=value["publication_authorized"],
            execution_authorized=value["execution_authorized"],
            recovered_after_commit=value["recovered_after_commit"],
            diagnostics=tuple(diagnostics),
            steps=tuple(RuntimeTranscriptStepV1.from_dict(item) for item in steps),
            version=value["version"],
            result_root=value["result_root"],
        )


@runtime_checkable
class RuntimeIntegrationAdapterV1(Protocol):
    """One black-box runtime composition; requests never contain an oracle."""

    implementation_id: str
    conformance_version: str

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1: ...

    def read_driver_checkpoint_v1(
        self,
        checkpoint_wire: str,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        """Read one receipt through the adapter's own checkpoint decoder."""
        ...

    def open_recovered_governance_reader_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> GovernanceStateReaderV2 | None:
        """Return the reader recreated after this request's Store restart."""
        ...

    def open_recovered_certificate_states_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> (
        tuple[
            VerifiedCommitCertificateStateV2,
            VerifiedCommitCertificateStateV2 | None,
        ]
        | None
    ):
        """Return observed/successor handles rebound to one restarted Store."""
        ...


def _optional_baseline_request(value: object) -> BaselineOutputRequestV2 | None:
    return None if value is None else BaselineOutputRequestV2.from_dict(value)


def _optional_baseline_result(value: object) -> BaselineOutputResultV2 | None:
    return None if value is None else BaselineOutputResultV2.from_dict(value)


def _optional_commit_outcome(value: object) -> CommitDecisionOutcomeV2 | None:
    return None if value is None else CommitDecisionOutcomeV2.from_dict(value)


def _optional_commit_observation(value: object) -> RuntimeCommitObservationV1 | None:
    return None if value is None else RuntimeCommitObservationV1.from_dict(value)


def _optional_finality(value: object) -> CommitFinalityProjectionV2 | None:
    return None if value is None else CommitFinalityProjectionV2.from_dict(value)


_CONTROL_FIELDS = frozenset(
    {
        "version",
        "wall_clock_timed_out",
        "cancel_requested",
        "repeat_invocation",
        "recover_after_commit",
        "supersede_before_recovery",
        "advance_permission_before_recovery",
        "advance_stop_before_recovery",
        "omit_permission",
        "inject_cas_conflict",
    }
)
_STEP_FIELDS = frozenset(
    {
        "version",
        "sequence",
        "layer",
        "artifact_version",
        "artifact_root",
        "predecessor_root",
        "step_root",
    }
)
_COMMIT_OBSERVATION_FIELDS = frozenset(
    {"version", "outcome", "observed_finality", "successor_finality"}
)
_REQUEST_FIELDS = frozenset(
    {
        "version",
        "scenario_id",
        "scope",
        "compatibility_claim",
        "capability",
        "authority_domain",
        "issuer_grant",
        "driver_request",
        "driver_result",
        "verified_signal_requests",
        "baseline_request",
        "commit_observation",
        "control",
        "successor_request",
        "request_root",
        "contender_request",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "version",
        "implementation_id",
        "request_root",
        "disposition",
        "compatibility_manifest_root",
        "compatibility_report_version",
        "compatibility_ok",
        "plan_document",
        "plan_root",
        "driver_receipts",
        "driver_checkpoint_wire",
        "driver_restarted_receipt",
        "driver_checkpoint_root",
        "governance_result",
        "commit_outcome",
        "trace_checkpoint",
        "delivery_eligible",
        "publication_authorized",
        "execution_authorized",
        "recovered_after_commit",
        "diagnostics",
        "steps",
        "result_root",
    }
)


__all__ = [
    "RuntimeControlInputV1",
    "RuntimeCommitObservationV1",
    "RuntimeIntegrationAdapterV1",
    "RuntimeTranscriptDispositionV1",
    "RuntimeTranscriptRequestV1",
    "RuntimeTranscriptResultV1",
    "RuntimeTranscriptStepV1",
]
