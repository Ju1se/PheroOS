"""Complete-replacement durable state contracts for Commit Certificate v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

from pheroos.governance._commit_certificate_v2.common import (
    MAX_COMMIT_CERTIFICATE_ATTESTATIONS_V2,
    MAX_COMMIT_CERTIFICATE_SNAPSHOT_BYTES_V2,
    _canonical_bytes,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
    _root,
)
from pheroos.governance._commit_certificate_v2.enums import (
    CommitCertificateMutationKindV2,
    CommitCertificateStatusV2,
)
from pheroos.governance._commit_certificate_v2.portable_envelope import (
    PortableCommitCertificateV2,
)


COMMIT_CERTIFICATE_IDENTITY_BINDING_SCHEMA_V2 = (
    "pheroos-commit-certificate-identity-binding-v2"
)
COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2 = "pheroos-commit-certificate-snapshot-v2"
COMMIT_CERTIFICATE_STATE_SCHEMA_V2 = "pheroos-commit-certificate-state-v2"


def commit_certificate_stream_ref_v2(
    scope_ref: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    values = tuple(
        _require_text(value, f"commit certificate stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    material = b"\x00".join(item.encode("utf-8") for item in values)
    return "authority:commit-certificate-v2:" + sha256(material).hexdigest()


def commit_certificate_transition_id_v2(stream_ref: str, mutation_ref: str) -> str:
    stream = _require_text(stream_ref, "commit certificate transition stream_ref")
    mutation = _require_text(mutation_ref, "commit certificate transition mutation_ref")
    material = stream.encode("utf-8") + b"\x00" + mutation.encode("utf-8")
    return "transition:commit-certificate-v2:" + sha256(material).hexdigest()


COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2 = "genesis"
COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2 = _root(
    "genesis-snapshot", {"schema": COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2}
)
COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2 = _root(
    "genesis-history", {"schema": COMMIT_CERTIFICATE_STATE_SCHEMA_V2}
)


@dataclass(frozen=True, slots=True)
class CommitCertificateIdentityBindingV2:
    certificate_id: str
    body_root: str
    first_envelope_root: str
    schema: str = COMMIT_CERTIFICATE_IDENTITY_BINDING_SCHEMA_V2
    binding_root: str = ""

    _root_field: ClassVar[str] = "binding_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_CERTIFICATE_IDENTITY_BINDING_SCHEMA_V2:
            raise ValueError("commit certificate identity schema is unsupported")
        _require_text(self.certificate_id, "commit certificate identity")
        _require_root(self.body_root, "commit certificate identity body_root")
        _require_root(
            self.first_envelope_root,
            "commit certificate identity first_envelope_root",
        )
        _install_root(
            self, "binding_root", self.binding_root, "identity-binding", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "certificate_id": self.certificate_id,
            "body_root": self.body_root,
            "first_envelope_root": self.first_envelope_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "binding_root": self.binding_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitCertificateIdentityBindingV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "certificate_id",
                    "body_root",
                    "first_envelope_root",
                    "binding_root",
                }
            ),
            "commit certificate identity binding v2",
        )
        decoded = cls(
            schema=cast(str, value["schema"]),
            certificate_id=cast(str, value["certificate_id"]),
            body_root=cast(str, value["body_root"]),
            first_envelope_root=cast(str, value["first_envelope_root"]),
            binding_root=cast(str, value["binding_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit certificate identity binding v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class CommitCertificateSnapshotV2:
    domain_root: str
    scope_ref: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    stream_ref: str
    mutation_ref: str
    mutation_issuer_ref: str
    transition_id: str
    revision: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    current_step: int
    mutation_kind: CommitCertificateMutationKindV2
    status: CommitCertificateStatusV2
    certificate: PortableCommitCertificateV2
    identity_bindings: Sequence[CommitCertificateIdentityBindingV2]
    envelope_roots: Sequence[str]
    conflicting_body_roots: Sequence[str]
    reason_codes: Sequence[str]
    parent_history_root: str
    parent_history_count: int
    history_root: str
    history_count: int
    source_context_root: str
    schema: str = COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2
    state_schema: str = COMMIT_CERTIFICATE_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    state_root: str = ""
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        self._validate_context()
        bindings = _canonical_identity_bindings(self.identity_bindings)
        object.__setattr__(self, "identity_bindings", bindings)
        envelopes = _canonical_texts(
            self.envelope_roots,
            "commit certificate envelope roots",
            maximum=MAX_COMMIT_CERTIFICATE_ATTESTATIONS_V2 * 4,
        )
        conflicts = _canonical_texts(
            self.conflicting_body_roots,
            "commit certificate conflicting body roots",
            maximum=MAX_COMMIT_CERTIFICATE_ATTESTATIONS_V2 * 4,
            allow_empty=True,
        )
        for item in (*envelopes, *conflicts):
            _require_root(item, "commit certificate snapshot root entry")
        object.__setattr__(self, "envelope_roots", envelopes)
        object.__setattr__(self, "conflicting_body_roots", conflicts)
        reasons = _canonical_texts(
            self.reason_codes,
            "commit certificate reason codes",
            maximum=64,
        )
        object.__setattr__(self, "reason_codes", reasons)
        self._validate_status()
        _install_root(self, "state_root", self.state_root, "state", self._state_body())
        expected_history = _root(
            "history",
            {
                "parent_history_root": self.parent_history_root,
                "parent_history_count": self.parent_history_count,
                "transition_id": self.transition_id,
                "state_root": self.state_root,
            },
        )
        if self.history_root not in ("", expected_history):
            raise ValueError("commit certificate history root is mismatched")
        object.__setattr__(self, "history_root", expected_history)
        _install_root(
            self, "snapshot_root", self.snapshot_root, "snapshot", self._body()
        )
        if (
            len(_canonical_bytes(self.to_dict()))
            > MAX_COMMIT_CERTIFICATE_SNAPSHOT_BYTES_V2
        ):
            raise ValueError("commit certificate snapshot exceeds its byte bound")

    def _validate_context(self) -> None:
        self._validate_version_and_types()
        self._validate_continuity()

    def _validate_version_and_types(self) -> None:
        if (
            self.schema != COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2
            or self.state_schema != COMMIT_CERTIFICATE_STATE_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("commit certificate snapshot version is unsupported")
        for field in (
            "scope_ref",
            "protocol_ref",
            "run_ref",
            "target_ref",
            "stream_ref",
            "mutation_ref",
            "mutation_issuer_ref",
            "transition_id",
            "parent_transition_id",
        ):
            _require_text(getattr(self, field), f"commit certificate {field}")
        for field in (
            "domain_root",
            "parent_snapshot_root",
            "parent_history_root",
            "source_context_root",
        ):
            _require_root(getattr(self, field), f"commit certificate {field}")
        for field in (
            "revision",
            "parent_revision",
            "current_step",
            "parent_history_count",
            "history_count",
        ):
            _require_count(getattr(self, field), f"commit certificate {field}")
        if type(self.mutation_kind) is not CommitCertificateMutationKindV2:
            raise TypeError("commit certificate mutation kind is invalid")
        if type(self.status) is not CommitCertificateStatusV2:
            raise TypeError("commit certificate status is invalid")
        if type(self.certificate) is not PortableCommitCertificateV2:
            raise TypeError("commit certificate snapshot requires an exact certificate")

    def _validate_continuity(self) -> None:
        if self.stream_ref != commit_certificate_stream_ref_v2(
            self.scope_ref, self.protocol_ref, self.run_ref, self.target_ref
        ):
            raise ValueError("commit certificate stream identity is mismatched")
        if self.transition_id != commit_certificate_transition_id_v2(
            self.stream_ref, self.mutation_ref
        ):
            raise ValueError("commit certificate transition identity is mismatched")
        if self.revision < 1 or self.parent_revision != self.revision - 1:
            raise ValueError("commit certificate revision is not contiguous")
        if self.history_count != self.parent_history_count + 1:
            raise ValueError("commit certificate history count is not contiguous")
        if self.revision == 1 and (
            self.parent_transition_id != COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2
            or self.parent_snapshot_root != COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2
            or self.parent_history_root != COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2
            or self.parent_history_count != 0
        ):
            raise ValueError("commit certificate genesis lineage is mismatched")

    def _validate_status(self) -> None:
        self._validate_body_binding()
        self._validate_identity_status()

    def _validate_body_binding(self) -> None:
        body = self.certificate.body
        if (
            body.domain_root != self.domain_root
            or body.scope_ref != self.scope_ref
            or body.protocol_ref != self.protocol_ref
            or body.run_ref != self.run_ref
            or body.target_ref != self.target_ref
        ):
            raise ValueError("commit certificate snapshot body is cross-bound")
        if self.certificate.envelope_root not in self.envelope_roots:
            raise ValueError(
                "commit certificate current envelope is absent from history"
            )

    def _validate_identity_status(self) -> None:
        body = self.certificate.body
        matching = tuple(
            item
            for item in self.identity_bindings
            if item.certificate_id == self.certificate.certificate_id
        )
        if not matching:
            raise ValueError("commit certificate identity has no durable binding")
        if self.status is CommitCertificateStatusV2.VERIFIED:
            if self.conflicting_body_roots:
                raise ValueError("verified commit certificate cannot carry conflicts")
            if matching[0].body_root != body.body_root:
                raise ValueError("verified commit certificate identity is mismatched")
        elif not self.conflicting_body_roots:
            raise ValueError("conflicting commit certificate requires conflict roots")
        if self.mutation_kind is CommitCertificateMutationKindV2.CONFLICT:
            if self.status is not CommitCertificateStatusV2.CONFLICT:
                raise ValueError("commit certificate conflict mutation must be sticky")
        elif self.status is not CommitCertificateStatusV2.VERIFIED:
            raise ValueError(
                "non-conflict commit certificate mutation must be verified"
            )

    def _state_body(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "mutation_kind": self.mutation_kind.value,
            "certificate_body_root": self.certificate.body.body_root,
            "certificate_envelope_root": self.certificate.envelope_root,
            "identity_binding_roots": [
                item.binding_root for item in self.identity_bindings
            ],
            "envelope_roots": list(self.envelope_roots),
            "conflicting_body_roots": list(self.conflicting_body_roots),
            "current_step": self.current_step,
        }

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state_schema": self.state_schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "stream_ref": self.stream_ref,
            "mutation_ref": self.mutation_ref,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "transition_id": self.transition_id,
            "revision": self.revision,
            "parent_revision": self.parent_revision,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "current_step": self.current_step,
            "mutation_kind": self.mutation_kind.value,
            "status": self.status.value,
            "certificate": self.certificate.to_dict(),
            "identity_bindings": [item.to_dict() for item in self.identity_bindings],
            "envelope_roots": list(self.envelope_roots),
            "conflicting_body_roots": list(self.conflicting_body_roots),
            "reason_codes": list(self.reason_codes),
            "parent_history_root": self.parent_history_root,
            "parent_history_count": self.parent_history_count,
            "history_root": self.history_root,
            "history_count": self.history_count,
            "source_context_root": self.source_context_root,
            "state_root": self.state_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitCertificateSnapshotV2:
        value = _exact_mapping(
            payload, _SNAPSHOT_FIELDS, "commit certificate snapshot v2"
        )
        try:
            mutation = CommitCertificateMutationKindV2(
                cast(str, value["mutation_kind"])
            )
            status = CommitCertificateStatusV2(cast(str, value["status"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit certificate snapshot enum is unsupported") from exc
        decoded = cls(
            schema=cast(str, value["schema"]),
            state_schema=cast(str, value["state_schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            stream_ref=cast(str, value["stream_ref"]),
            mutation_ref=cast(str, value["mutation_ref"]),
            mutation_issuer_ref=cast(str, value["mutation_issuer_ref"]),
            transition_id=cast(str, value["transition_id"]),
            revision=cast(int, value["revision"]),
            parent_revision=cast(int, value["parent_revision"]),
            parent_transition_id=cast(str, value["parent_transition_id"]),
            parent_snapshot_root=cast(str, value["parent_snapshot_root"]),
            current_step=cast(int, value["current_step"]),
            mutation_kind=mutation,
            status=status,
            certificate=PortableCommitCertificateV2.from_dict(value["certificate"]),
            identity_bindings=tuple(
                CommitCertificateIdentityBindingV2.from_dict(item)
                for item in _exact_array(
                    value["identity_bindings"], "commit certificate identities"
                )
            ),
            envelope_roots=tuple(
                cast(str, item)
                for item in _exact_array(
                    value["envelope_roots"], "commit certificate envelopes"
                )
            ),
            conflicting_body_roots=tuple(
                cast(str, item)
                for item in _exact_array(
                    value["conflicting_body_roots"], "commit certificate conflicts"
                )
            ),
            reason_codes=tuple(
                cast(str, item)
                for item in _exact_array(
                    value["reason_codes"], "commit certificate reasons"
                )
            ),
            parent_history_root=cast(str, value["parent_history_root"]),
            parent_history_count=cast(int, value["parent_history_count"]),
            history_root=cast(str, value["history_root"]),
            history_count=cast(int, value["history_count"]),
            source_context_root=cast(str, value["source_context_root"]),
            state_root=cast(str, value["state_root"]),
            snapshot_root=cast(str, value["snapshot_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit certificate snapshot v2"
        )
        return decoded


def _canonical_identity_bindings(
    values: Sequence[CommitCertificateIdentityBindingV2],
) -> tuple[CommitCertificateIdentityBindingV2, ...]:
    if type(values) not in (list, tuple):
        raise TypeError("commit certificate identities must be an exact sequence")
    bindings = tuple(values)
    if not 1 <= len(bindings) <= MAX_COMMIT_CERTIFICATE_ATTESTATIONS_V2 * 4:
        raise ValueError("commit certificate identity count is invalid")
    if any(type(item) is not CommitCertificateIdentityBindingV2 for item in bindings):
        raise TypeError("commit certificate identity binding is noncanonical")
    ordered = tuple(
        sorted(bindings, key=lambda item: item.certificate_id.encode("utf-8"))
    )
    if len({item.certificate_id for item in ordered}) != len(ordered):
        raise ValueError("commit certificate identities must be unique")
    return ordered


_SNAPSHOT_FIELDS = frozenset(
    {
        "schema",
        "state_schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
        "mutation_ref",
        "mutation_issuer_ref",
        "transition_id",
        "revision",
        "parent_revision",
        "parent_transition_id",
        "parent_snapshot_root",
        "current_step",
        "mutation_kind",
        "status",
        "certificate",
        "identity_bindings",
        "envelope_roots",
        "conflicting_body_roots",
        "reason_codes",
        "parent_history_root",
        "parent_history_count",
        "history_root",
        "history_count",
        "source_context_root",
        "state_root",
        "snapshot_root",
    }
)


__all__ = [
    "COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2",
    "COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2",
    "COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2",
    "COMMIT_CERTIFICATE_IDENTITY_BINDING_SCHEMA_V2",
    "COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2",
    "COMMIT_CERTIFICATE_STATE_SCHEMA_V2",
    "CommitCertificateIdentityBindingV2",
    "CommitCertificateSnapshotV2",
    "commit_certificate_stream_ref_v2",
    "commit_certificate_transition_id_v2",
]
