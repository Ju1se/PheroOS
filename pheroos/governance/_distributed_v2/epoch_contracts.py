"""Portable certified static-epoch transition records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_ROOTS_V2,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)
from pheroos.governance._distributed_v2.policy import DistributedPolicyBindingV2


DISTRIBUTED_EPOCH_TRANSITION_CERTIFICATE_SCHEMA_V2 = (
    "pheroos-distributed-epoch-transition-certificate-v2"
)


@dataclass(frozen=True, slots=True)
class DistributedEpochTransitionCertificateV2:
    domain_root: str
    scope_ref: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    transition_certificate_ref: str
    from_epoch: int | None
    to_epoch: int
    transition_rule: str
    policy_binding: DistributedPolicyBindingV2
    manifest_root: str
    commit_policy_root: str
    membership_stream_ref: str
    membership_revision: int
    membership_transition_id: str
    membership_snapshot_root: str
    membership_head_root: str
    membership_root: str
    verification_stream_ref: str
    verification_revision: int
    verification_transition_id: str
    verification_snapshot_root: str
    verification_head_root: str
    verification_set_root: str
    prior_epoch_snapshot_root: str
    prior_proposal_head_root: str
    prior_witness_head_root: str
    prior_certificate_head_root: str
    conflict_history_roots: Sequence[str]
    required_action_refs: Sequence[str]
    issued_at_step: int
    issuer_ref: str
    provenance_ref: str
    source_trace_roots: Sequence[str]
    schema: str = DISTRIBUTED_EPOCH_TRANSITION_CERTIFICATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    certificate_root: str = ""

    _root_field: ClassVar[str] = "certificate_root"

    def __post_init__(self) -> None:
        self._validate_fields()
        self._validate_transition()
        conflicts, actions, traces = self._canonical_sequences()
        object.__setattr__(self, "conflict_history_roots", conflicts)
        object.__setattr__(self, "required_action_refs", actions)
        object.__setattr__(self, "source_trace_roots", traces)
        _install_root(
            self,
            "certificate_root",
            self.certificate_root,
            "epoch-transition-certificate",
            self._body(),
        )

    def _validate_fields(self) -> None:
        if (
            self.schema != DISTRIBUTED_EPOCH_TRANSITION_CERTIFICATE_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("distributed epoch certificate version is unsupported")
        for field in _EPOCH_TEXT_FIELDS:
            _require_text(getattr(self, field), f"distributed epoch {field}")
        for field in _EPOCH_ROOT_FIELDS:
            _require_root(
                getattr(self, field),
                f"distributed epoch {field}",
                allow_empty=field.startswith("prior_"),
            )
        if type(self.policy_binding) is not DistributedPolicyBindingV2:
            raise TypeError("distributed epoch requires exact policy binding")
        if self.transition_rule != self.policy_binding.epoch_transition_rule:
            raise ValueError("distributed epoch transition rule is mismatched")

    def _validate_transition(self) -> None:
        if self.from_epoch is None:
            if self.prior_epoch_snapshot_root:
                raise ValueError(
                    "distributed genesis epoch cannot name a prior snapshot"
                )
        else:
            previous = _require_count(self.from_epoch, "distributed from_epoch")
            if previous >= (2**53 - 1) or self.to_epoch != previous + 1:
                raise ValueError("distributed epoch must increment exactly once")
            if not self.prior_epoch_snapshot_root:
                raise ValueError("distributed epoch transition lacks prior snapshot")
        _require_count(self.to_epoch, "distributed to_epoch")
        _require_count(self.issued_at_step, "distributed epoch issued_at_step")
        _require_count(
            self.membership_revision,
            "distributed epoch membership_revision",
            minimum=1,
        )
        _require_count(
            self.verification_revision,
            "distributed epoch verification_revision",
            minimum=1,
        )

    def _canonical_sequences(
        self,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        conflicts = _canonical_texts(
            self.conflict_history_roots,
            "distributed epoch conflict roots",
            maximum=MAX_DISTRIBUTED_ROOTS_V2,
            roots=True,
        )
        actions = _canonical_texts(
            self.required_action_refs,
            "distributed epoch action refs",
            maximum=2,
            allow_empty=False,
        )
        if "epoch_transition" not in actions or any(
            item not in {"epoch_transition", "recovery"} for item in actions
        ):
            raise ValueError("distributed epoch action refs are not least privilege")
        if "recovery" in actions and not conflicts:
            raise ValueError("distributed recovery requires committed conflict history")
        if conflicts and self.from_epoch is not None and "recovery" not in actions:
            raise ValueError("frozen distributed epoch requires recovery authority")
        traces = _canonical_texts(
            self.source_trace_roots,
            "distributed epoch trace roots",
            maximum=MAX_DISTRIBUTED_ROOTS_V2,
            allow_empty=False,
            roots=True,
        )
        return conflicts, actions, traces

    def _body(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "from_epoch": self.from_epoch,
            "to_epoch": self.to_epoch,
            "policy_binding": self.policy_binding.to_dict(),
            "membership_revision": self.membership_revision,
            "verification_revision": self.verification_revision,
            "conflict_history_roots": list(self.conflict_history_roots),
            "required_action_refs": list(self.required_action_refs),
            "issued_at_step": self.issued_at_step,
            "source_trace_roots": list(self.source_trace_roots),
        }
        for field in _EPOCH_TEXT_FIELDS + _EPOCH_ROOT_FIELDS:
            body[field] = getattr(self, field)
        return body

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "certificate_root": self.certificate_root}

    @classmethod
    def from_dict(cls, payload: object) -> DistributedEpochTransitionCertificateV2:
        value = _exact_mapping(payload, _EPOCH_FIELDS, "distributed epoch certificate")
        from_epoch_raw = value["from_epoch"]
        if from_epoch_raw is not None and type(from_epoch_raw) is not int:
            raise TypeError("distributed epoch from_epoch is invalid")
        decoded = cls(
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            transition_certificate_ref=cast(str, value["transition_certificate_ref"]),
            from_epoch=from_epoch_raw,
            to_epoch=cast(int, value["to_epoch"]),
            transition_rule=cast(str, value["transition_rule"]),
            policy_binding=DistributedPolicyBindingV2(
                policy_root=cast(str, _policy(value)["policy_root"]),
                membership_size=cast(int, _policy(value)["membership_size"]),
                max_byzantine_faults=cast(int, _policy(value)["max_byzantine_faults"]),
                witness_quorum=cast(int, _policy(value)["witness_quorum"]),
                witness_ttl_steps=cast(int, _policy(value)["witness_ttl_steps"]),
                minimum_failure_domain_diversity=cast(
                    int, _policy(value)["minimum_failure_domain_diversity"]
                ),
                epoch_transition_rule=cast(
                    str, _policy(value)["epoch_transition_rule"]
                ),
                binding_root=cast(str, _policy(value)["binding_root"]),
            ),
            manifest_root=cast(str, value["manifest_root"]),
            commit_policy_root=cast(str, value["commit_policy_root"]),
            membership_stream_ref=cast(str, value["membership_stream_ref"]),
            membership_revision=cast(int, value["membership_revision"]),
            membership_transition_id=cast(str, value["membership_transition_id"]),
            membership_snapshot_root=cast(str, value["membership_snapshot_root"]),
            membership_head_root=cast(str, value["membership_head_root"]),
            membership_root=cast(str, value["membership_root"]),
            verification_stream_ref=cast(str, value["verification_stream_ref"]),
            verification_revision=cast(int, value["verification_revision"]),
            verification_transition_id=cast(str, value["verification_transition_id"]),
            verification_snapshot_root=cast(str, value["verification_snapshot_root"]),
            verification_head_root=cast(str, value["verification_head_root"]),
            verification_set_root=cast(str, value["verification_set_root"]),
            prior_epoch_snapshot_root=cast(str, value["prior_epoch_snapshot_root"]),
            prior_proposal_head_root=cast(str, value["prior_proposal_head_root"]),
            prior_witness_head_root=cast(str, value["prior_witness_head_root"]),
            prior_certificate_head_root=cast(str, value["prior_certificate_head_root"]),
            conflict_history_roots=cast(
                Sequence[str],
                _exact_array(
                    value["conflict_history_roots"],
                    "distributed epoch conflict roots",
                ),
            ),
            required_action_refs=cast(
                Sequence[str],
                _exact_array(
                    value["required_action_refs"],
                    "distributed epoch action refs",
                    maximum=2,
                    allow_empty=False,
                ),
            ),
            issued_at_step=cast(int, value["issued_at_step"]),
            issuer_ref=cast(str, value["issuer_ref"]),
            provenance_ref=cast(str, value["provenance_ref"]),
            source_trace_roots=cast(
                Sequence[str],
                _exact_array(
                    value["source_trace_roots"],
                    "distributed epoch trace roots",
                    allow_empty=False,
                ),
            ),
            certificate_root=cast(str, value["certificate_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "distributed epoch certificate"
        )
        return decoded


def _policy(value: dict[str, object]) -> dict[str, object]:
    return _exact_mapping(
        value["policy_binding"],
        frozenset(
            {
                "policy_root",
                "membership_size",
                "max_byzantine_faults",
                "witness_quorum",
                "witness_ttl_steps",
                "minimum_failure_domain_diversity",
                "epoch_transition_rule",
                "binding_root",
            }
        ),
        "distributed epoch policy binding",
    )


_EPOCH_TEXT_FIELDS = (
    "scope_ref",
    "protocol_ref",
    "run_ref",
    "target_ref",
    "transition_certificate_ref",
    "transition_rule",
    "membership_stream_ref",
    "membership_transition_id",
    "verification_stream_ref",
    "verification_transition_id",
    "issuer_ref",
    "provenance_ref",
)
_EPOCH_ROOT_FIELDS = (
    "domain_root",
    "manifest_root",
    "commit_policy_root",
    "membership_snapshot_root",
    "membership_head_root",
    "membership_root",
    "verification_snapshot_root",
    "verification_head_root",
    "verification_set_root",
    "prior_epoch_snapshot_root",
    "prior_proposal_head_root",
    "prior_witness_head_root",
    "prior_certificate_head_root",
)
_EPOCH_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "from_epoch",
        "to_epoch",
        "policy_binding",
        "membership_revision",
        "verification_revision",
        "conflict_history_roots",
        "required_action_refs",
        "issued_at_step",
        "source_trace_roots",
        "certificate_root",
        *_EPOCH_TEXT_FIELDS,
        *_EPOCH_ROOT_FIELDS,
    }
)


__all__ = [
    "DISTRIBUTED_EPOCH_TRANSITION_CERTIFICATE_SCHEMA_V2",
    "DistributedEpochTransitionCertificateV2",
]
