"""Portable issuer records and opaque, store-bound authority handles.

This module is private until the complete scoped-authority profile is active.
Portable records are canonical data.  Capability and session objects are local
handles: they deliberately have no wire representation and retain the exact
writer object selected by the trusted host.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import (
    Any,
    NoReturn,
    Protocol,
    SupportsIndex,
    cast,
    final,
    runtime_checkable,
)
import unicodedata

from pheroos.governance._scoped_authority_primitives_v2 import (
    _canonical_bytes as _canonical_bytes,
    _compute_root as _compute_root,
    _install_root as _install_root,
    _require_root as _require_root,
    _require_text as _require_text,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
    AuthorityDiagnosticCodeV2,
)

from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AuthorityDomainV2,
)


GOVERNANCE_ISSUER_GRANT_SCHEMA_V2 = "pheroos-governance-issuer-grant-v2"
ISSUER_GRANT_VERIFICATION_SCHEMA_V2 = "pheroos-issuer-grant-verification-v2"
GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2 = (
    "pheroos-governance-verified-signal-request-v2"
)
GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2 = (
    "pheroos-governance-domain-retirement-request-v2"
)

_STREAM_PREFIX = "authority"
_SIGNAL_STATUSES = frozenset({"verified", "rejected"})
_CAPABILITY_TOKEN = object()
_SESSION_TOKEN = object()


class GovernanceIssuerOperationV2(StrEnum):
    """Closed least-privilege issuer operation registry."""

    VERIFY_SIGNAL = "verify_signal"
    EVALUATE_QUORUM = "evaluate_quorum"
    QUALIFY_EVIDENCE = "qualify_evidence"
    RESOLVE_STOP = "resolve_stop"
    ADVANCE_REPLAY = "advance_replay"
    ISSUE_ACTION_PERMISSION = "issue_action_permission"
    AUTHORIZE_OUTPUT = "authorize_output"
    RETIRE_DOMAIN = "retire_domain"


class GovernanceAuthorityBindingErrorV2(ValueError):
    """Typed programmer-boundary failure for an opaque authority binding."""

    __slots__ = ("code", "path")

    def __init__(
        self,
        code: AuthorityDiagnosticCodeV2,
        path: str,
    ) -> None:
        if type(code) is not AuthorityDiagnosticCodeV2:
            raise TypeError("authority binding error requires the Protocol diagnostic")
        _require_json_pointer(path)
        self.code = code
        self.path = path
        super().__init__(f"{code.value}:{path}")


@dataclass(frozen=True, slots=True)
class GovernanceIssuerGrantV2:
    """Portable issuer grant; possession of this record is not authority."""

    domain_root: str
    scope_ref: str
    issuer_ref: str
    grant_ref: str
    grant_binding_ref: str
    operations: tuple[GovernanceIssuerOperationV2, ...]
    target_refs: tuple[str, ...]
    action_refs: tuple[str, ...]
    issued_epoch: int
    not_before_epoch: int
    expires_at_epoch: int
    revocation_generation: int
    schema: str = GOVERNANCE_ISSUER_GRANT_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    grant_root: str = ""

    def __post_init__(self) -> None:
        _require_root(self.domain_root, "issuer grant domain_root")
        _require_text(self.scope_ref, "issuer grant scope_ref")
        _require_text(self.issuer_ref, "issuer grant issuer_ref")
        _require_text(self.grant_ref, "issuer grant grant_ref")
        _require_root(self.grant_binding_ref, "issuer grant grant_binding_ref")
        _require_operation_tuple(self.operations)
        _require_ref_tuple(self.target_refs, "issuer grant target_refs")
        _require_ref_tuple(self.action_refs, "issuer grant action_refs")
        _require_epoch(self.issued_epoch, "issuer grant issued_epoch")
        _require_epoch(self.not_before_epoch, "issuer grant not_before_epoch")
        _require_epoch(self.expires_at_epoch, "issuer grant expires_at_epoch")
        _require_epoch(
            self.revocation_generation,
            "issuer grant revocation_generation",
        )
        if not (self.issued_epoch <= self.not_before_epoch <= self.expires_at_epoch):
            raise ValueError("issuer grant epoch bounds are inconsistent")
        _require_exact_version(
            self.schema,
            GOVERNANCE_ISSUER_GRANT_SCHEMA_V2,
            "issuer grant schema",
        )
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "issuer grant canonical_version",
        )
        _install_root(self, "grant_root", self.grant_root, "issuer-grant", self._body())

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "issuer_ref": self.issuer_ref,
            "grant_ref": self.grant_ref,
            "grant_binding_ref": self.grant_binding_ref,
            "operations": [item.value for item in self.operations],
            "target_refs": list(self.target_refs),
            "action_refs": list(self.action_refs),
            "issued_epoch": self.issued_epoch,
            "not_before_epoch": self.not_before_epoch,
            "expires_at_epoch": self.expires_at_epoch,
            "revocation_generation": self.revocation_generation,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "grant_root": self.grant_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.grant_root

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceIssuerGrantV2:
        value = _exact_object(
            payload,
            {
                "schema",
                "canonical_version",
                "domain_root",
                "scope_ref",
                "issuer_ref",
                "grant_ref",
                "grant_binding_ref",
                "operations",
                "target_refs",
                "action_refs",
                "issued_epoch",
                "not_before_epoch",
                "expires_at_epoch",
                "revocation_generation",
                "grant_root",
            },
            "issuer grant",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            issuer_ref=value["issuer_ref"],
            grant_ref=value["grant_ref"],
            grant_binding_ref=value["grant_binding_ref"],
            operations=_operations_from_wire(value["operations"]),
            target_refs=_refs_from_wire(value["target_refs"], "issuer target_refs"),
            action_refs=_refs_from_wire(value["action_refs"], "issuer action_refs"),
            issued_epoch=value["issued_epoch"],
            not_before_epoch=value["not_before_epoch"],
            expires_at_epoch=value["expires_at_epoch"],
            revocation_generation=value["revocation_generation"],
            schema=value["schema"],
            canonical_version=value["canonical_version"],
            grant_root=value["grant_root"],
        )


@dataclass(frozen=True, slots=True)
class IssuerGrantVerificationV2:
    """Portable verifier result; only an accepted matching result can bind."""

    grant_root: str
    grant_binding_ref: str
    verifier_ref: str
    accepted: bool
    verified_epoch: int
    schema: str = ISSUER_GRANT_VERIFICATION_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    verification_root: str = ""

    def __post_init__(self) -> None:
        _require_root(self.grant_root, "issuer verification grant_root")
        _require_root(
            self.grant_binding_ref,
            "issuer verification grant_binding_ref",
        )
        _require_text(self.verifier_ref, "issuer verification verifier_ref")
        if type(self.accepted) is not bool:
            raise TypeError("issuer verification accepted must be an exact bool")
        _require_epoch(self.verified_epoch, "issuer verification verified_epoch")
        _require_exact_version(
            self.schema,
            ISSUER_GRANT_VERIFICATION_SCHEMA_V2,
            "issuer verification schema",
        )
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "issuer verification canonical_version",
        )
        _install_root(
            self,
            "verification_root",
            self.verification_root,
            "issuer-grant-verification",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "grant_root": self.grant_root,
            "grant_binding_ref": self.grant_binding_ref,
            "verifier_ref": self.verifier_ref,
            "accepted": self.accepted,
            "verified_epoch": self.verified_epoch,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "verification_root": self.verification_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.verification_root

    @classmethod
    def from_dict(cls, payload: object) -> IssuerGrantVerificationV2:
        value = _exact_object(
            payload,
            {
                "schema",
                "canonical_version",
                "grant_root",
                "grant_binding_ref",
                "verifier_ref",
                "accepted",
                "verified_epoch",
                "verification_root",
            },
            "issuer grant verification",
        )
        return cls(
            grant_root=value["grant_root"],
            grant_binding_ref=value["grant_binding_ref"],
            verifier_ref=value["verifier_ref"],
            accepted=value["accepted"],
            verified_epoch=value["verified_epoch"],
            schema=value["schema"],
            canonical_version=value["canonical_version"],
            verification_root=value["verification_root"],
        )


@runtime_checkable
class IssuerGrantVerifierV2(Protocol):
    """Host-selected authenticated-profile grant verifier boundary."""

    def verify_issuer_grant_v2(
        self,
        grant: GovernanceIssuerGrantV2,
        *,
        observed_epoch: int,
    ) -> IssuerGrantVerificationV2: ...


@dataclass(frozen=True, slots=True)
class GovernanceVerifiedSignalRequestV2:
    """Portable VERIFY_SIGNAL request bound to one deterministic stream."""

    domain_root: str
    scope_ref: str
    run_ref: str
    request_ref: str
    transition_id: str
    signal_ref: str
    target_ref: str
    signal_root: str
    evidence_root: str
    status: str
    observed_epoch: int
    stream_ref: str = ""
    schema: str = GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    def __post_init__(self) -> None:
        _require_root(self.domain_root, "verified signal request domain_root")
        _require_text(self.scope_ref, "verified signal request scope_ref")
        _require_text(self.run_ref, "verified signal request run_ref")
        _require_text(self.request_ref, "verified signal request request_ref")
        _require_transition_id(
            self.transition_id,
            "verified signal request transition_id",
        )
        _require_text(self.signal_ref, "verified signal request signal_ref")
        _require_text(self.target_ref, "verified signal request target_ref")
        _require_root(self.signal_root, "verified signal request signal_root")
        _require_root(self.evidence_root, "verified signal request evidence_root")
        if type(self.status) is not str or self.status not in _SIGNAL_STATUSES:
            raise ValueError("verified signal request status is unsupported")
        _require_epoch(self.observed_epoch, "verified signal request observed_epoch")
        computed_stream = governance_verified_signal_stream_ref_v2(
            self.scope_ref,
            self.signal_ref,
            self.target_ref,
        )
        _install_derived_text(
            self,
            "stream_ref",
            self.stream_ref,
            computed_stream,
            "verified signal request stream_ref",
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2,
            "verified signal request schema",
        )
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "verified signal request canonical_version",
        )
        _install_root(
            self,
            "request_root",
            self.request_root,
            "verified-signal-request",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "request_ref": self.request_ref,
            "transition_id": self.transition_id,
            "signal_ref": self.signal_ref,
            "target_ref": self.target_ref,
            "signal_root": self.signal_root,
            "evidence_root": self.evidence_root,
            "status": self.status,
            "observed_epoch": self.observed_epoch,
            "stream_ref": self.stream_ref,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.request_root

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceVerifiedSignalRequestV2:
        value = _exact_object(
            payload,
            {
                "schema",
                "canonical_version",
                "domain_root",
                "scope_ref",
                "run_ref",
                "request_ref",
                "transition_id",
                "signal_ref",
                "target_ref",
                "signal_root",
                "evidence_root",
                "status",
                "observed_epoch",
                "stream_ref",
                "request_root",
            },
            "verified signal request",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            run_ref=value["run_ref"],
            request_ref=value["request_ref"],
            transition_id=value["transition_id"],
            signal_ref=value["signal_ref"],
            target_ref=value["target_ref"],
            signal_root=value["signal_root"],
            evidence_root=value["evidence_root"],
            status=value["status"],
            observed_epoch=value["observed_epoch"],
            stream_ref=value["stream_ref"],
            schema=value["schema"],
            canonical_version=value["canonical_version"],
            request_root=value["request_root"],
        )


@dataclass(frozen=True, slots=True)
class GovernanceDomainRetirementRequestV2:
    """Portable RETIRE_DOMAIN request over the complete declared stream set."""

    domain_root: str
    scope_ref: str
    run_ref: str
    request_ref: str
    transition_id: str
    stream_refs: tuple[str, ...]
    reason_ref: str
    observed_epoch: int
    schema: str = GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    def __post_init__(self) -> None:
        _require_root(self.domain_root, "domain retirement request domain_root")
        _require_text(self.scope_ref, "domain retirement request scope_ref")
        _require_text(self.run_ref, "domain retirement request run_ref")
        _require_text(self.request_ref, "domain retirement request request_ref")
        _require_transition_id(
            self.transition_id,
            "domain retirement request transition_id",
        )
        _require_ref_tuple(self.stream_refs, "domain retirement request stream_refs")
        if len(self.stream_refs) > 127:
            raise ValueError("domain retirement request stream_refs exceed the bound")
        _require_text(self.reason_ref, "domain retirement request reason_ref")
        _require_epoch(self.observed_epoch, "domain retirement request observed_epoch")
        _require_exact_version(
            self.schema,
            GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2,
            "domain retirement request schema",
        )
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "domain retirement request canonical_version",
        )
        _install_root(
            self,
            "request_root",
            self.request_root,
            "domain-retirement-request",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "request_ref": self.request_ref,
            "transition_id": self.transition_id,
            "stream_refs": list(self.stream_refs),
            "reason_ref": self.reason_ref,
            "observed_epoch": self.observed_epoch,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.request_root

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceDomainRetirementRequestV2:
        value = _exact_object(
            payload,
            {
                "schema",
                "canonical_version",
                "domain_root",
                "scope_ref",
                "run_ref",
                "request_ref",
                "transition_id",
                "stream_refs",
                "reason_ref",
                "observed_epoch",
                "request_root",
            },
            "domain retirement request",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            run_ref=value["run_ref"],
            request_ref=value["request_ref"],
            transition_id=value["transition_id"],
            stream_refs=_refs_from_wire(
                value["stream_refs"],
                "domain retirement stream_refs",
            ),
            reason_ref=value["reason_ref"],
            observed_epoch=value["observed_epoch"],
            schema=value["schema"],
            canonical_version=value["canonical_version"],
            request_root=value["request_root"],
        )


def governance_issuer_grant_stream_ref_v2(scope_ref: str, grant_ref: str) -> str:
    """Derive the canonical per-scope issuer-grant authority stream."""

    _require_text(scope_ref, "issuer grant stream scope_ref")
    _require_text(grant_ref, "issuer grant stream grant_ref")
    return _stream_ref("issuer-grant", (scope_ref, grant_ref))


def governance_verified_signal_stream_ref_v2(
    scope_ref: str,
    signal_ref: str,
    target_ref: str,
) -> str:
    """Derive the canonical per-scope verified-signal authority stream."""

    _require_text(scope_ref, "verified signal stream scope_ref")
    _require_text(signal_ref, "verified signal stream signal_ref")
    _require_text(target_ref, "verified signal stream target_ref")
    return _stream_ref("verified-signal", (scope_ref, signal_ref, target_ref))


@dataclass(frozen=True, slots=True)
class _GovernanceIssuerCapabilityStateV2:
    _owner: object
    store: object
    domain: AuthorityDomainV2
    grant: GovernanceIssuerGrantV2
    verification: IssuerGrantVerificationV2 | None
    run_ref: str
    observed_epoch: int
    _snapshot: tuple[
        object,
        object,
        AuthorityDomainV2,
        bytes,
        bytes,
        bytes | None,
        str,
        int,
    ]


@final
class GovernanceIssuerCapabilityV2:
    """Opaque local handle proving custody of one exact writer binding."""

    __slots__ = ("_state", "_token")

    def __new__(cls, *_args: object, **_kwargs: object) -> GovernanceIssuerCapabilityV2:
        raise TypeError("GovernanceIssuerCapabilityV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("GovernanceIssuerCapabilityV2 is final")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("GovernanceIssuerCapabilityV2 is immutable")

    def __copy__(self) -> GovernanceIssuerCapabilityV2:
        _governance_issuer_capability_state_v2(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> GovernanceIssuerCapabilityV2:
        _governance_issuer_capability_state_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("GovernanceIssuerCapabilityV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("GovernanceIssuerCapabilityV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("GovernanceIssuerCapabilityV2 is not portable")

    def __repr__(self) -> str:
        return "<GovernanceIssuerCapabilityV2 redacted>"

    @property
    def domain_root(self) -> str:
        return _governance_issuer_capability_state_v2(self).domain.domain_root

    @property
    def profile(self) -> str:
        return _governance_issuer_capability_state_v2(self).domain.profile

    @property
    def scope_ref(self) -> str:
        return _governance_issuer_capability_state_v2(self).grant.scope_ref

    @property
    def issuer_ref(self) -> str:
        return _governance_issuer_capability_state_v2(self).grant.issuer_ref

    @property
    def grant_ref(self) -> str:
        return _governance_issuer_capability_state_v2(self).grant.grant_ref

    @property
    def grant_root(self) -> str:
        return _governance_issuer_capability_state_v2(self).grant.grant_root

    @property
    def grant_binding_ref(self) -> str:
        return _governance_issuer_capability_state_v2(self).grant.grant_binding_ref

    @property
    def run_ref(self) -> str:
        return _governance_issuer_capability_state_v2(self).run_ref

    @property
    def operations(self) -> tuple[GovernanceIssuerOperationV2, ...]:
        return _governance_issuer_capability_state_v2(self).grant.operations

    @property
    def target_refs(self) -> tuple[str, ...]:
        return _governance_issuer_capability_state_v2(self).grant.target_refs

    @property
    def action_refs(self) -> tuple[str, ...]:
        return _governance_issuer_capability_state_v2(self).grant.action_refs

    @property
    def issued_epoch(self) -> int:
        return _governance_issuer_capability_state_v2(self).grant.issued_epoch

    @property
    def not_before_epoch(self) -> int:
        return _governance_issuer_capability_state_v2(self).grant.not_before_epoch

    @property
    def expires_at_epoch(self) -> int:
        return _governance_issuer_capability_state_v2(self).grant.expires_at_epoch

    @property
    def revocation_generation(self) -> int:
        return _governance_issuer_capability_state_v2(self).grant.revocation_generation

    @property
    def observed_epoch(self) -> int:
        return _governance_issuer_capability_state_v2(self).observed_epoch

    @property
    def verifier_ref(self) -> str | None:
        verification = _governance_issuer_capability_state_v2(self).verification
        return None if verification is None else verification.verifier_ref

    @property
    def verification_root(self) -> str | None:
        verification = _governance_issuer_capability_state_v2(self).verification
        return None if verification is None else verification.verification_root


@dataclass(frozen=True, slots=True)
class _GovernanceAuthoritySessionStateV2:
    _owner: object
    store: object
    capability: GovernanceIssuerCapabilityV2
    domain_root: str
    scope_ref: str
    run_ref: str
    request_ref: str
    request_root: str
    operation: GovernanceIssuerOperationV2
    observed_epoch: int
    grant_ref: str
    grant_root: str
    grant_binding_ref: str
    grant_expected_revision: int
    grant_expected_root: str
    lifecycle_expected_revision: int
    lifecycle_expected_root: str
    target_refs: tuple[str, ...]
    action_refs: tuple[str, ...]
    _snapshot: tuple[object, ...]


@final
class GovernanceAuthoritySessionV2:
    """Opaque request-bound authority session over one exact writer object."""

    __slots__ = ("_state", "_token")

    def __new__(cls, *_args: object, **_kwargs: object) -> GovernanceAuthoritySessionV2:
        raise TypeError("GovernanceAuthoritySessionV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("GovernanceAuthoritySessionV2 is final")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("GovernanceAuthoritySessionV2 is immutable")

    def __copy__(self) -> GovernanceAuthoritySessionV2:
        _governance_authority_session_state_v2(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> GovernanceAuthoritySessionV2:
        _governance_authority_session_state_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("GovernanceAuthoritySessionV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("GovernanceAuthoritySessionV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("GovernanceAuthoritySessionV2 is not portable")

    def __repr__(self) -> str:
        return "<GovernanceAuthoritySessionV2 redacted>"

    @property
    def domain_root(self) -> str:
        return _governance_authority_session_state_v2(self).domain_root

    @property
    def profile(self) -> str:
        state = _governance_authority_session_state_v2(self)
        return _governance_issuer_capability_state_v2(state.capability).domain.profile

    @property
    def scope_ref(self) -> str:
        return _governance_authority_session_state_v2(self).scope_ref

    @property
    def run_ref(self) -> str:
        return _governance_authority_session_state_v2(self).run_ref

    @property
    def request_ref(self) -> str:
        return _governance_authority_session_state_v2(self).request_ref

    @property
    def request_root(self) -> str:
        return _governance_authority_session_state_v2(self).request_root

    @property
    def operation(self) -> GovernanceIssuerOperationV2:
        return _governance_authority_session_state_v2(self).operation

    @property
    def observed_epoch(self) -> int:
        return _governance_authority_session_state_v2(self).observed_epoch

    @property
    def grant_ref(self) -> str:
        return _governance_authority_session_state_v2(self).grant_ref

    @property
    def grant_root(self) -> str:
        return _governance_authority_session_state_v2(self).grant_root

    @property
    def grant_binding_ref(self) -> str:
        return _governance_authority_session_state_v2(self).grant_binding_ref

    @property
    def grant_expected_revision(self) -> int:
        return _governance_authority_session_state_v2(self).grant_expected_revision

    @property
    def grant_expected_root(self) -> str:
        return _governance_authority_session_state_v2(self).grant_expected_root

    @property
    def lifecycle_expected_revision(self) -> int:
        return _governance_authority_session_state_v2(self).lifecycle_expected_revision

    @property
    def lifecycle_expected_root(self) -> str:
        return _governance_authority_session_state_v2(self).lifecycle_expected_root

    @property
    def target_refs(self) -> tuple[str, ...]:
        return _governance_authority_session_state_v2(self).target_refs

    @property
    def action_refs(self) -> tuple[str, ...]:
        return _governance_authority_session_state_v2(self).action_refs


def _make_governance_issuer_capability_v2(
    *,
    store: object,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    run_ref: str,
    observed_epoch: int,
    verification: IssuerGrantVerificationV2 | None = None,
) -> GovernanceIssuerCapabilityV2:
    """Trusted-host factory for one exact, non-portable writer binding."""

    if store is None:
        raise TypeError("issuer capability requires an exact store object")
    if type(domain) is not AuthorityDomainV2:
        raise TypeError("issuer capability requires AuthorityDomainV2")
    if type(grant) is not GovernanceIssuerGrantV2:
        raise TypeError("issuer capability requires GovernanceIssuerGrantV2")
    detached_grant = GovernanceIssuerGrantV2.from_dict(grant.to_dict())
    if (
        domain.domain_root != detached_grant.domain_root
        or domain.scope_ref != detached_grant.scope_ref
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/domain_root",
        )
    _require_text(run_ref, "issuer capability run_ref")
    _require_epoch(observed_epoch, "issuer capability observed_epoch")
    if (
        not detached_grant.not_before_epoch
        <= observed_epoch
        <= detached_grant.expires_at_epoch
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
            "/observed_epoch",
        )
    detached_verification = _validated_capability_verification_v2(
        domain,
        detached_grant,
        verification,
        observed_epoch,
    )
    verification_bytes = (
        None
        if detached_verification is None
        else detached_verification.canonical_bytes()
    )
    handle = object.__new__(GovernanceIssuerCapabilityV2)
    snapshot = (
        handle,
        store,
        domain,
        domain.canonical_bytes(),
        detached_grant.canonical_bytes(),
        verification_bytes,
        run_ref,
        observed_epoch,
    )
    state = _GovernanceIssuerCapabilityStateV2(
        _owner=handle,
        store=store,
        domain=domain,
        grant=detached_grant,
        verification=detached_verification,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
        _snapshot=snapshot,
    )
    object.__setattr__(handle, "_state", state)
    object.__setattr__(handle, "_token", _CAPABILITY_TOKEN)
    return handle


def _validated_capability_verification_v2(
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    verification: IssuerGrantVerificationV2 | None,
    observed_epoch: int,
) -> IssuerGrantVerificationV2 | None:
    if domain.profile == AUTHORITY_AUTHENTICATED_PROFILE_V2 and verification is None:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/verification",
        )
    if domain.profile == AUTHORITY_LOCAL_PROFILE_V2 and verification is not None:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/verification",
        )
    if verification is None:
        return None
    if type(verification) is not IssuerGrantVerificationV2:
        raise TypeError("issuer capability verification type is invalid")
    detached = IssuerGrantVerificationV2.from_dict(verification.to_dict())
    if (
        detached.accepted is not True
        or detached.grant_root != grant.grant_root
        or detached.grant_binding_ref != grant.grant_binding_ref
        or detached.verified_epoch != observed_epoch
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/verification",
        )
    return detached


def _governance_issuer_capability_state_v2(
    handle: object,
) -> _GovernanceIssuerCapabilityStateV2:
    """Return validated private state for sibling Governance operations."""

    if type(handle) is not GovernanceIssuerCapabilityV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
            "",
        )
    try:
        token = object.__getattribute__(handle, "_token")
        state = object.__getattribute__(handle, "_state")
    except AttributeError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
            "",
        ) from exc
    if (
        token is not _CAPABILITY_TOKEN
        or type(state) is not _GovernanceIssuerCapabilityStateV2
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
            "",
        )
    if type(state._snapshot) is not tuple or len(state._snapshot) != 8:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        )
    verification_bytes = (
        None if state.verification is None else state.verification.canonical_bytes()
    )
    expected = (
        state._owner,
        state.store,
        state.domain,
        state.domain.canonical_bytes(),
        state.grant.canonical_bytes(),
        verification_bytes,
        state.run_ref,
        state.observed_epoch,
    )
    if (
        state._owner is not handle
        or state._owner is not state._snapshot[0]
        or state.store is not state._snapshot[1]
        or state.domain is not state._snapshot[2]
        or expected[3:] != state._snapshot[3:]
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        )
    return state


def _make_governance_authority_session_v2(
    *,
    capability: GovernanceIssuerCapabilityV2,
    request_ref: str,
    request_root: str,
    operation: GovernanceIssuerOperationV2,
    run_ref: str,
    observed_epoch: int,
    grant_expected_revision: int,
    grant_expected_root: str,
    lifecycle_expected_revision: int,
    lifecycle_expected_root: str,
    target_refs: tuple[str, ...] = (),
    action_refs: tuple[str, ...] = (),
) -> GovernanceAuthoritySessionV2:
    """Bind one least-privilege capability to one exact portable request."""

    capability_state = _governance_issuer_capability_state_v2(capability)
    grant = capability_state.grant
    _require_root(request_root, "authority session request_root")
    if type(operation) is not GovernanceIssuerOperationV2:
        raise TypeError("authority session operation type is invalid")
    if operation not in grant.operations:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/operation",
        )
    _require_text(run_ref, "authority session run_ref")
    if run_ref != capability_state.run_ref:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/run_ref",
        )
    _require_text(request_ref, "authority session request_ref")
    _require_epoch(observed_epoch, "authority session observed_epoch")
    if (
        observed_epoch < capability_state.observed_epoch
        or not grant.not_before_epoch <= observed_epoch <= grant.expires_at_epoch
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
            "/observed_epoch",
        )
    _require_epoch(
        grant_expected_revision,
        "authority session grant_expected_revision",
    )
    _require_root(grant_expected_root, "authority session grant_expected_root")
    _require_epoch(
        lifecycle_expected_revision,
        "authority session lifecycle_expected_revision",
    )
    _require_root(
        lifecycle_expected_root,
        "authority session lifecycle_expected_root",
    )
    _require_ref_tuple(target_refs, "authority session target_refs")
    _require_ref_tuple(action_refs, "authority session action_refs")
    if target_refs and not set(target_refs) <= set(grant.target_refs):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/target_refs",
        )
    if action_refs and not set(action_refs) <= set(grant.action_refs):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/action_refs",
        )
    handle = object.__new__(GovernanceAuthoritySessionV2)
    snapshot: tuple[object, ...] = (
        handle,
        capability_state.store,
        capability,
        grant.domain_root,
        grant.scope_ref,
        run_ref,
        request_ref,
        request_root,
        operation,
        observed_epoch,
        grant.grant_ref,
        grant.grant_root,
        grant.grant_binding_ref,
        grant_expected_revision,
        grant_expected_root,
        lifecycle_expected_revision,
        lifecycle_expected_root,
        target_refs,
        action_refs,
    )
    state = _GovernanceAuthoritySessionStateV2(
        _owner=handle,
        store=capability_state.store,
        capability=capability,
        domain_root=grant.domain_root,
        scope_ref=grant.scope_ref,
        run_ref=run_ref,
        request_ref=request_ref,
        request_root=request_root,
        operation=operation,
        observed_epoch=observed_epoch,
        grant_ref=grant.grant_ref,
        grant_root=grant.grant_root,
        grant_binding_ref=grant.grant_binding_ref,
        grant_expected_revision=grant_expected_revision,
        grant_expected_root=grant_expected_root,
        lifecycle_expected_revision=lifecycle_expected_revision,
        lifecycle_expected_root=lifecycle_expected_root,
        target_refs=target_refs,
        action_refs=action_refs,
        _snapshot=snapshot,
    )
    object.__setattr__(handle, "_state", state)
    object.__setattr__(handle, "_token", _SESSION_TOKEN)
    return handle


def _governance_authority_session_state_v2(
    handle: object,
) -> _GovernanceAuthoritySessionStateV2:
    """Return validated request/session state for sibling Governance operations."""

    if type(handle) is not GovernanceAuthoritySessionV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
            "",
        )
    try:
        token = object.__getattribute__(handle, "_token")
        state = object.__getattribute__(handle, "_state")
    except AttributeError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
            "",
        ) from exc
    if (
        token is not _SESSION_TOKEN
        or type(state) is not _GovernanceAuthoritySessionStateV2
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
            "",
        )
    if type(state._snapshot) is not tuple or len(state._snapshot) != 19:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        )
    capability_state = _governance_issuer_capability_state_v2(state.capability)
    expected: tuple[object, ...] = (
        state._owner,
        state.store,
        state.capability,
        state.domain_root,
        state.scope_ref,
        state.run_ref,
        state.request_ref,
        state.request_root,
        state.operation,
        state.observed_epoch,
        state.grant_ref,
        state.grant_root,
        state.grant_binding_ref,
        state.grant_expected_revision,
        state.grant_expected_root,
        state.lifecycle_expected_revision,
        state.lifecycle_expected_root,
        state.target_refs,
        state.action_refs,
    )
    if (
        state._owner is not handle
        or state._owner is not state._snapshot[0]
        or state.store is not capability_state.store
        or state.store is not state._snapshot[1]
        or expected[2:] != state._snapshot[2:]
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        )
    return state


def _stream_ref(kind: str, bindings: tuple[str, ...]) -> str:
    for index, binding in enumerate(bindings):
        _require_text(binding, f"{kind} stream binding/{index}")
    payload = b"\x00".join(binding.encode("utf-8") for binding in bindings)
    digest = sha256(payload).hexdigest()
    return f"{_STREAM_PREFIX}:{kind}:{digest}"


def _install_derived_text(
    instance: object,
    attribute: str,
    supplied: object,
    computed: str,
    label: str,
) -> None:
    if type(supplied) is str and supplied == "":
        object.__setattr__(instance, attribute, computed)
        return
    _require_text(supplied, label)
    if supplied != computed:
        raise ValueError(f"{label} is mismatched")
    object.__setattr__(instance, attribute, computed)


def _require_exact_version(value: object, expected: str, label: str) -> None:
    if type(value) is not str or value != expected:
        raise ValueError(f"{label} is unsupported")


def _require_transition_id(value: object, label: str) -> str:
    transition_id = _require_text(value, label)
    if transition_id == "genesis":
        raise ValueError(f"{label} is reserved")
    return transition_id


def _require_epoch(value: object, label: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} must be a JSON-safe non-negative integer")
    return value


def _require_operation_tuple(
    value: object,
) -> tuple[GovernanceIssuerOperationV2, ...]:
    if type(value) is not tuple or not value:
        raise TypeError("issuer grant operations must be a non-empty exact tuple")
    operations = cast(tuple[object, ...], value)
    if any(type(item) is not GovernanceIssuerOperationV2 for item in operations):
        raise TypeError("issuer grant operations contain an invalid operation")
    typed = cast(tuple[GovernanceIssuerOperationV2, ...], operations)
    canonical = tuple(item for item in GovernanceIssuerOperationV2 if item in typed)
    if len(typed) != len(set(typed)) or typed != canonical:
        raise ValueError(
            "issuer grant operations must be unique and use canonical enum order"
        )
    return typed


def _require_ref_tuple(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{label} must be an exact tuple")
    refs = cast(tuple[object, ...], value)
    if any(type(item) is not str for item in refs):
        raise TypeError(f"{label} must contain only text")
    typed = cast(tuple[str, ...], refs)
    for index, item in enumerate(typed):
        _require_text(item, f"{label}/{index}")
    if len(typed) != len(set(typed)) or typed != tuple(
        sorted(typed, key=lambda item: item.encode("utf-8"))
    ):
        raise ValueError(f"{label} must be unique and UTF-8 sorted")
    return typed


def _operations_from_wire(value: object) -> tuple[GovernanceIssuerOperationV2, ...]:
    if type(value) is not list:
        raise TypeError("issuer grant operations wire must be an array")
    if any(type(item) is not str for item in value):
        raise TypeError("issuer grant operations wire must contain exact text")
    operations = tuple(GovernanceIssuerOperationV2(item) for item in value)
    return _require_operation_tuple(operations)


def _refs_from_wire(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise TypeError(f"{label} wire must be an array")
    return _require_ref_tuple(tuple(value), label)


def _exact_object(
    payload: object,
    fields: set[str],
    label: str,
) -> dict[str, Any]:
    if type(payload) is not dict:
        raise TypeError(f"{label} must be an exact object")
    if set(payload) != fields:
        raise ValueError(f"{label} fields are invalid")
    return cast(dict[str, Any], payload)


def _require_json_pointer(value: object) -> str:
    if type(value) is not str or (value and not value.startswith("/")):
        raise ValueError("authority binding error path must be a JSON pointer")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("authority binding error path must already use Unicode NFC")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("authority binding error path must encode as UTF-8") from exc
    for token in value.split("/")[1:]:
        index = 0
        while index < len(token):
            if token[index] != "~":
                index += 1
                continue
            if index + 1 >= len(token) or token[index + 1] not in "01":
                raise ValueError("authority binding error path escape is invalid")
            index += 2
    return value


__all__ = [
    "GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2",
    "GOVERNANCE_ISSUER_GRANT_SCHEMA_V2",
    "GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2",
    "ISSUER_GRANT_VERIFICATION_SCHEMA_V2",
    "GovernanceAuthorityBindingErrorV2",
    "GovernanceAuthoritySessionV2",
    "GovernanceDomainRetirementRequestV2",
    "GovernanceIssuerCapabilityV2",
    "GovernanceIssuerGrantV2",
    "GovernanceIssuerOperationV2",
    "GovernanceVerifiedSignalRequestV2",
    "IssuerGrantVerificationV2",
    "IssuerGrantVerifierV2",
    "governance_issuer_grant_stream_ref_v2",
    "governance_verified_signal_stream_ref_v2",
]
