"""Authority-domain, head, and prepared-transition v2 records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, ClassVar

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
)

from pheroos.governance._scoped_authority_primitives_v2 import _ROOT_PREFIX
from pheroos.governance._authority_store_v2_contracts.foundation import (
    AUTHORITY_DOMAIN_SCHEMA_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_HEAD_SCHEMA_V2,
    GOVERNANCE_STATE_SCHEMA_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2,
    _CanonicalRootRecordV2,
    _DOMAIN_PROFILES,
    _compute_root,
    _exact_object,
    _freeze_json_mapping,
    _install_exact_computed,
    _install_root,
    _portable_json,
    _require_exact_version,
    _require_revision,
    _require_root,
    _require_text,
    _validate_common_binding,
)


@dataclass(frozen=True, slots=True)
class AuthorityDomainV2(_CanonicalRootRecordV2):
    """Exact authority-policy selection bound to one opaque scope."""

    policy_version: str
    profile: str
    wire_version: str
    canonical_version: str
    ledger_version: str
    state_store_version: str
    trace_batch_version: str
    read_set_version: str
    scope_ref: str
    schema: str = AUTHORITY_DOMAIN_SCHEMA_V2
    domain_root: str = ""

    _root_field: ClassVar[str] = "domain_root"

    def __post_init__(self) -> None:
        _require_exact_version(
            self.policy_version,
            AUTHORITY_POLICY_VERSION_V2,
            "authority domain policy_version",
        )
        if type(self.profile) is not str or self.profile not in _DOMAIN_PROFILES:
            raise ValueError("authority domain profile is unsupported")
        _require_exact_version(
            self.wire_version,
            AUTHORITY_WIRE_VERSION_V2,
            "authority domain wire_version",
        )
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "authority domain canonical_version",
        )
        _require_exact_version(
            self.ledger_version,
            AUTHORITY_LEDGER_VERSION_V2,
            "authority domain ledger_version",
        )
        _require_exact_version(
            self.state_store_version,
            GOVERNANCE_STATE_STORE_VERSION_V2,
            "authority domain state_store_version",
        )
        _require_exact_version(
            self.trace_batch_version,
            GOVERNANCE_TRACE_BATCH_VERSION_V2,
            "authority domain trace_batch_version",
        )
        _require_exact_version(
            self.read_set_version,
            GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
            "authority domain read_set_version",
        )
        _require_text(self.scope_ref, "authority domain scope_ref")
        _require_exact_version(
            self.schema,
            AUTHORITY_DOMAIN_SCHEMA_V2,
            "authority domain schema",
        )
        _install_root(
            self,
            "domain_root",
            self.domain_root,
            "domain",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "policy_version": self.policy_version,
            "profile": self.profile,
            "wire_version": self.wire_version,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "state_store_version": self.state_store_version,
            "trace_batch_version": self.trace_batch_version,
            "read_set_version": self.read_set_version,
            "scope_ref": self.scope_ref,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "domain_root": self.domain_root}

    @classmethod
    def from_dict(cls, payload: object) -> AuthorityDomainV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "policy_version",
                    "profile",
                    "wire_version",
                    "canonical_version",
                    "ledger_version",
                    "state_store_version",
                    "trace_batch_version",
                    "read_set_version",
                    "scope_ref",
                    "domain_root",
                }
            ),
            "authority domain v2",
        )
        return cls(
            policy_version=value["policy_version"],
            profile=value["profile"],
            wire_version=value["wire_version"],
            canonical_version=value["canonical_version"],
            ledger_version=value["ledger_version"],
            state_store_version=value["state_store_version"],
            trace_batch_version=value["trace_batch_version"],
            read_set_version=value["read_set_version"],
            scope_ref=value["scope_ref"],
            schema=value["schema"],
            domain_root=value["domain_root"],
        )


def governance_authority_state_root_v2(
    scope_ref: str,
    stream_ref: str,
    state_records: Mapping[str, Any],
) -> str:
    """Root one complete, immutable authority stream state projection."""

    _require_text(scope_ref, "authority state scope_ref")
    _require_text(stream_ref, "authority state stream_ref")
    frozen = _freeze_json_mapping(state_records, "state_records")
    body = {
        "schema": GOVERNANCE_STATE_SCHEMA_V2,
        "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
        "ledger_version": AUTHORITY_LEDGER_VERSION_V2,
        "scope_ref": scope_ref,
        "stream_ref": stream_ref,
        "state_records": _portable_json(frozen),
    }
    return _compute_root("state", body)


GOVERNANCE_GENESIS_PARENT_ROOT_V2 = (
    "sha256:"
    + sha256((_ROOT_PREFIX + "genesis-parent").encode("utf-8") + b"\x00").hexdigest()
)


@dataclass(frozen=True, slots=True)
class GovernanceHeadV2(_CanonicalRootRecordV2):
    """One exact, immutable authority stream head observation."""

    domain_root: str
    scope_ref: str
    stream_ref: str
    revision: int
    parent_root: str
    state_root: str
    transition_id: str
    batch_root: str
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    ledger_version: str = AUTHORITY_LEDGER_VERSION_V2
    schema: str = GOVERNANCE_HEAD_SCHEMA_V2
    head_root: str = ""

    _root_field: ClassVar[str] = "head_root"

    def __post_init__(self) -> None:
        _validate_common_binding(
            canonical_version=self.canonical_version,
            ledger_version=self.ledger_version,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_HEAD_SCHEMA_V2,
            "governance head schema",
        )
        _require_text(self.stream_ref, "governance head stream_ref")
        _require_revision(self.revision, "governance head revision")
        _require_root(self.parent_root, "governance head parent_root")
        _require_root(self.state_root, "governance head state_root")
        _require_text(self.transition_id, "governance head transition_id")
        _require_root(self.batch_root, "governance head batch_root")
        if self.revision == 0:
            empty_state_root = governance_authority_state_root_v2(
                self.scope_ref,
                self.stream_ref,
                {},
            )
            if (
                self.parent_root != GOVERNANCE_GENESIS_PARENT_ROOT_V2
                or self.state_root != empty_state_root
                or self.transition_id != "genesis"
                or self.batch_root != GOVERNANCE_GENESIS_PARENT_ROOT_V2
            ):
                raise ValueError("governance genesis head fields are inconsistent")
        if self.revision > 0 and self.transition_id == "genesis":
            raise ValueError("non-genesis governance head cannot use genesis identity")
        _install_root(self, "head_root", self.head_root, "head", self._root_body())

    @classmethod
    def genesis(cls, domain: AuthorityDomainV2, stream_ref: str) -> GovernanceHeadV2:
        if type(domain) is not AuthorityDomainV2:
            raise TypeError("governance genesis head requires AuthorityDomainV2")
        state_root = governance_authority_state_root_v2(
            domain.scope_ref,
            stream_ref,
            {},
        )
        return cls(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref=stream_ref,
            revision=0,
            parent_root=GOVERNANCE_GENESIS_PARENT_ROOT_V2,
            state_root=state_root,
            transition_id="genesis",
            batch_root=GOVERNANCE_GENESIS_PARENT_ROOT_V2,
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "stream_ref": self.stream_ref,
            "revision": self.revision,
            "parent_root": self.parent_root,
            "state_root": self.state_root,
            "transition_id": self.transition_id,
            "batch_root": self.batch_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "head_root": self.head_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceHeadV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "ledger_version",
                    "domain_root",
                    "scope_ref",
                    "stream_ref",
                    "revision",
                    "parent_root",
                    "state_root",
                    "transition_id",
                    "batch_root",
                    "head_root",
                }
            ),
            "governance head v2",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            stream_ref=value["stream_ref"],
            revision=value["revision"],
            parent_root=value["parent_root"],
            state_root=value["state_root"],
            transition_id=value["transition_id"],
            batch_root=value["batch_root"],
            canonical_version=value["canonical_version"],
            ledger_version=value["ledger_version"],
            schema=value["schema"],
            head_root=value["head_root"],
        )


@dataclass(frozen=True, slots=True)
class PreparedGovernanceTransitionV2(_CanonicalRootRecordV2):
    """Complete replacement state prepared against one canonical read-set."""

    domain_root: str
    scope_ref: str
    stream_ref: str
    transition_id: str
    expected_revision: int
    expected_root: str
    read_set_root: str
    state_records: Mapping[str, Any]
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    ledger_version: str = AUTHORITY_LEDGER_VERSION_V2
    schema: str = PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2
    state_root: str = ""
    transition_root: str = ""

    _root_field: ClassVar[str] = "transition_root"

    def __post_init__(self) -> None:
        _validate_common_binding(
            canonical_version=self.canonical_version,
            ledger_version=self.ledger_version,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
        )
        _require_exact_version(
            self.schema,
            PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2,
            "prepared governance transition schema",
        )
        _require_text(self.stream_ref, "prepared transition stream_ref")
        if self.stream_ref == GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2:
            raise ValueError("prepared transition cannot target lifecycle stream")
        _require_text(self.transition_id, "prepared transition id")
        if self.transition_id == "genesis":
            raise ValueError("prepared transition cannot use genesis identity")
        _require_revision(
            self.expected_revision,
            "prepared transition expected_revision",
        )
        _require_root(self.expected_root, "prepared transition expected_root")
        _require_root(self.read_set_root, "prepared transition read_set_root")
        frozen = _freeze_json_mapping(self.state_records, "state_records")
        object.__setattr__(self, "state_records", frozen)
        computed_state_root = governance_authority_state_root_v2(
            self.scope_ref,
            self.stream_ref,
            frozen,
        )
        _install_exact_computed(
            self,
            "state_root",
            self.state_root,
            computed_state_root,
            "prepared transition state_root",
        )
        _install_root(
            self,
            "transition_root",
            self.transition_root,
            "transition",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "expected_revision": self.expected_revision,
            "expected_root": self.expected_root,
            "read_set_root": self.read_set_root,
            "state_records": _portable_json(self.state_records),
            "state_root": self.state_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "transition_root": self.transition_root}

    @classmethod
    def from_dict(cls, payload: object) -> PreparedGovernanceTransitionV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "ledger_version",
                    "domain_root",
                    "scope_ref",
                    "stream_ref",
                    "transition_id",
                    "expected_revision",
                    "expected_root",
                    "read_set_root",
                    "state_records",
                    "state_root",
                    "transition_root",
                }
            ),
            "prepared governance transition v2",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            stream_ref=value["stream_ref"],
            transition_id=value["transition_id"],
            expected_revision=value["expected_revision"],
            expected_root=value["expected_root"],
            read_set_root=value["read_set_root"],
            state_records=value["state_records"],
            canonical_version=value["canonical_version"],
            ledger_version=value["ledger_version"],
            schema=value["schema"],
            state_root=value["state_root"],
            transition_root=value["transition_root"],
        )
