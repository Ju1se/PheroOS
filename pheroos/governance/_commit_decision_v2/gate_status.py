"""Same-step gate projection used by sealed Decision v2 evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.governance._commit_decision_v2.common import (
    _canonical_roots,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_bool,
    _require_canonical_wire,
    _require_count,
)


COMMIT_DECISION_GATE_STATUS_SCHEMA_V2 = "pheroos-commit-decision-gate-status-v2"
_FIELDS = frozenset(
    {
        "schema",
        "current_step",
        "stop_clear",
        "permission_allowed",
        "risk_current",
        "membership_current",
        "verification_current",
        "evidence_current",
        "support_current",
        "blocker_roots",
        "reason_codes",
        "status_root",
    }
)


@dataclass(frozen=True, slots=True)
class CommitDecisionGateStatusV2:
    current_step: int
    stop_clear: bool
    permission_allowed: bool
    risk_current: bool
    membership_current: bool
    verification_current: bool
    evidence_current: bool
    support_current: bool
    blocker_roots: Sequence[str]
    reason_codes: Sequence[str]
    schema: str = COMMIT_DECISION_GATE_STATUS_SCHEMA_V2
    status_root: str = ""

    _root_field: ClassVar[str] = "status_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_DECISION_GATE_STATUS_SCHEMA_V2:
            raise ValueError("commit decision gate status schema is unsupported")
        _require_count(self.current_step, "commit decision gate status current_step")
        for field in (
            "stop_clear",
            "permission_allowed",
            "risk_current",
            "membership_current",
            "verification_current",
            "evidence_current",
            "support_current",
        ):
            _require_bool(
                getattr(self, field),
                f"commit decision gate status {field}",
            )
        roots = _canonical_roots(
            self.blocker_roots,
            "commit decision gate status blocker_roots",
        )
        reasons = _canonical_texts(
            self.reason_codes,
            "commit decision gate status reason_codes",
        )
        clear = all(
            (
                self.stop_clear,
                self.permission_allowed,
                self.risk_current,
                self.membership_current,
                self.verification_current,
                self.evidence_current,
                self.support_current,
            )
        )
        if not clear and not reasons:
            raise ValueError("commit decision false gate requires a reason")
        if clear and any(
            not reason.startswith(("invalid:", "safety:")) for reason in reasons
        ):
            raise ValueError(
                "clear commit gates allow only invalid or safety meta reasons"
            )
        object.__setattr__(self, "blocker_roots", roots)
        object.__setattr__(self, "reason_codes", reasons)
        _install_root(
            self,
            "status_root",
            self.status_root,
            "gate-status",
            self._body(),
        )

    @property
    def all_clear(self) -> bool:
        return not self.reason_codes

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "current_step": self.current_step,
            "stop_clear": self.stop_clear,
            "permission_allowed": self.permission_allowed,
            "risk_current": self.risk_current,
            "membership_current": self.membership_current,
            "verification_current": self.verification_current,
            "evidence_current": self.evidence_current,
            "support_current": self.support_current,
            "blocker_roots": list(self.blocker_roots),
            "reason_codes": list(self.reason_codes),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "status_root": self.status_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionGateStatusV2:
        value = _exact_mapping(payload, _FIELDS, "commit decision gate status v2")
        blocker_roots = tuple(
            cast(str, item)
            for item in _exact_array(
                value["blocker_roots"],
                "commit decision gate status blocker_roots",
            )
        )
        reason_codes = tuple(
            cast(str, item)
            for item in _exact_array(
                value["reason_codes"],
                "commit decision gate status reason_codes",
            )
        )
        decoded = cls(
            current_step=cast(int, value["current_step"]),
            stop_clear=cast(bool, value["stop_clear"]),
            permission_allowed=cast(bool, value["permission_allowed"]),
            risk_current=cast(bool, value["risk_current"]),
            membership_current=cast(bool, value["membership_current"]),
            verification_current=cast(bool, value["verification_current"]),
            evidence_current=cast(bool, value["evidence_current"]),
            support_current=cast(bool, value["support_current"]),
            blocker_roots=blocker_roots,
            reason_codes=reason_codes,
            schema=cast(str, value["schema"]),
            status_root=cast(str, value["status_root"]),
        )
        _require_canonical_wire(
            payload,
            decoded.to_dict(),
            "commit decision gate status v2",
        )
        return decoded


__all__ = ("CommitDecisionGateStatusV2",)
