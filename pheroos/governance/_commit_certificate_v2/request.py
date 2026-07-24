"""Portable issuance request for Commit Certificate v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

from pheroos.governance._commit_certificate_v2.common import (
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)
from pheroos.governance._commit_certificate_v2.portable_envelope import (
    PortableCommitCertificateV2,
)
from pheroos.governance._commit_certificate_v2.state_contracts import (
    COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2,
    commit_certificate_stream_ref_v2,
    commit_certificate_transition_id_v2,
)


COMMIT_CERTIFICATE_REQUEST_SCHEMA_V2 = "pheroos-commit-certificate-request-v2"


@dataclass(frozen=True, slots=True)
class CommitCertificateRequestV2:
    domain_root: str
    scope_ref: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    mutation_ref: str
    mutation_issuer_ref: str
    current_step: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    certificate: PortableCommitCertificateV2
    schema: str = COMMIT_CERTIFICATE_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    stream_ref: str = ""
    transition_id: str = ""
    request_root: str = ""

    _root_field: ClassVar[str] = "request_root"

    def __post_init__(self) -> None:
        if (
            self.schema != COMMIT_CERTIFICATE_REQUEST_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("commit certificate request version is unsupported")
        for field in (
            "scope_ref",
            "protocol_ref",
            "run_ref",
            "target_ref",
            "mutation_ref",
            "mutation_issuer_ref",
            "parent_transition_id",
        ):
            _require_text(getattr(self, field), f"commit certificate request {field}")
        for field in ("domain_root", "parent_snapshot_root"):
            _require_root(getattr(self, field), f"commit certificate request {field}")
        for field in ("observed_epoch", "current_step", "parent_revision"):
            _require_count(getattr(self, field), f"commit certificate request {field}")
        if type(self.certificate) is not PortableCommitCertificateV2:
            raise TypeError("commit certificate request requires an exact envelope")
        body = self.certificate.body
        if (
            body.domain_root != self.domain_root
            or body.scope_ref != self.scope_ref
            or body.protocol_ref != self.protocol_ref
            or body.run_ref != self.run_ref
            or body.target_ref != self.target_ref
            or body.epoch != self.observed_epoch
        ):
            raise ValueError("commit certificate request body is cross-bound")
        expected_stream = commit_certificate_stream_ref_v2(
            self.scope_ref, self.protocol_ref, self.run_ref, self.target_ref
        )
        if self.stream_ref not in ("", expected_stream):
            raise ValueError("commit certificate request stream_ref is mismatched")
        object.__setattr__(self, "stream_ref", expected_stream)
        expected_transition = commit_certificate_transition_id_v2(
            expected_stream, self.mutation_ref
        )
        if self.transition_id not in ("", expected_transition):
            raise ValueError("commit certificate request transition_id is mismatched")
        object.__setattr__(self, "transition_id", expected_transition)
        if self.parent_revision == 0 and (
            self.parent_transition_id != COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2
            or self.parent_snapshot_root != COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2
        ):
            raise ValueError("commit certificate request genesis parent is mismatched")
        _install_root(self, "request_root", self.request_root, "request", self._body())

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "mutation_ref": self.mutation_ref,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "current_step": self.current_step,
            "parent_revision": self.parent_revision,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "certificate": self.certificate.to_dict(),
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitCertificateRequestV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "domain_root",
                    "scope_ref",
                    "protocol_ref",
                    "run_ref",
                    "target_ref",
                    "observed_epoch",
                    "mutation_ref",
                    "mutation_issuer_ref",
                    "current_step",
                    "parent_revision",
                    "parent_transition_id",
                    "parent_snapshot_root",
                    "certificate",
                    "stream_ref",
                    "transition_id",
                    "request_root",
                }
            ),
            "commit certificate request v2",
        )
        decoded = cls(
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            observed_epoch=cast(int, value["observed_epoch"]),
            mutation_ref=cast(str, value["mutation_ref"]),
            mutation_issuer_ref=cast(str, value["mutation_issuer_ref"]),
            current_step=cast(int, value["current_step"]),
            parent_revision=cast(int, value["parent_revision"]),
            parent_transition_id=cast(str, value["parent_transition_id"]),
            parent_snapshot_root=cast(str, value["parent_snapshot_root"]),
            certificate=PortableCommitCertificateV2.from_dict(value["certificate"]),
            stream_ref=cast(str, value["stream_ref"]),
            transition_id=cast(str, value["transition_id"]),
            request_root=cast(str, value["request_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit certificate request v2"
        )
        return decoded


__all__ = ["COMMIT_CERTIFICATE_REQUEST_SCHEMA_V2", "CommitCertificateRequestV2"]
