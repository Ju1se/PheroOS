from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Any


CONFORMANCE_REPORT_VERSION = "pheroos-conformance-report-v2"
CONFORMANCE_REPORT_SCHEMA_ID = "https://pheroos.dev/schemas/conformance-report-v2.schema.json"
PHEROOS_IMPLEMENTATION_ID = "pheroos.protocol-core"
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class ConformanceSubjectKind(StrEnum):
    MANIFEST = "manifest"
    REFERENCE_BEHAVIOR = "reference-behavior"
    IMPLEMENTATION_TCK = "implementation-tck"
    SOURCE_ABI = "source-abi"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("conformance check name must be nonblank")
        if not isinstance(self.ok, bool):
            raise TypeError("conformance check status must be boolean")
        if not isinstance(self.detail, str):
            raise TypeError("conformance check detail must be text")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class ConformanceReport:
    target: str
    checks: tuple[CheckResult, ...] = ()
    profile: str = ""
    report_version: str = CONFORMANCE_REPORT_VERSION
    report_schema_id: str = CONFORMANCE_REPORT_SCHEMA_ID
    subject_kind: ConformanceSubjectKind = ConformanceSubjectKind.MANIFEST
    implementation_identity: str = PHEROOS_IMPLEMENTATION_ID
    artifact_digest: str = ""

    def __post_init__(self) -> None:
        checks = tuple(self.checks)
        object.__setattr__(self, "checks", checks)
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("conformance report target must be nonblank")
        if self.report_version != CONFORMANCE_REPORT_VERSION:
            raise ValueError("unsupported conformance report version")
        if self.report_schema_id != CONFORMANCE_REPORT_SCHEMA_ID:
            raise ValueError("conformance report schema id does not match its version")
        try:
            subject_kind = ConformanceSubjectKind(self.subject_kind)
        except (TypeError, ValueError) as exc:
            raise ValueError("unsupported conformance report subject kind") from exc
        object.__setattr__(self, "subject_kind", subject_kind)
        if not isinstance(self.implementation_identity, str) or not self.implementation_identity.strip():
            raise ValueError("conformance implementation identity must be nonblank")
        if not isinstance(self.profile, str) or not self.profile.strip():
            raise ValueError("conformance profile must be nonblank")
        if not isinstance(self.artifact_digest, str) or not _DIGEST_PATTERN.fullmatch(
            self.artifact_digest
        ):
            raise ValueError("conformance artifact digest must be canonical sha256")
        if any(not isinstance(check, CheckResult) for check in checks):
            raise TypeError("conformance report checks must be canonical CheckResult values")
        names = tuple(check.name for check in checks)
        if len(names) != len(set(names)):
            raise ValueError("conformance report check names must be unique")

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "$schema": self.report_schema_id,
            "report_version": self.report_version,
            "subject_kind": self.subject_kind.value,
            "implementation_identity": self.implementation_identity,
            "target": self.target,
            "profile": self.profile,
            "artifact_digest": self.artifact_digest,
            "ok": self.ok,
            "check_projection": [check.to_dict() for check in self.checks],
            # Keep the established key through the Draft ABI migration.  It is
            # byte-for-byte the deterministic projection above, not a second
            # source of check truth.
            "checks": [check.to_dict() for check in self.checks],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ConformanceReport:
        fields = {
            "$schema",
            "report_version",
            "subject_kind",
            "implementation_identity",
            "target",
            "profile",
            "artifact_digest",
            "ok",
            "check_projection",
            "checks",
        }
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ValueError("conformance report fields are invalid")
        if payload["check_projection"] != payload["checks"]:
            raise ValueError("conformance report check projection is inconsistent")
        raw_checks = payload["checks"]
        if not isinstance(raw_checks, list):
            raise ValueError("conformance report checks must be an array")
        checks: list[CheckResult] = []
        for item in raw_checks:
            if not isinstance(item, dict) or set(item) != {"name", "ok", "detail"}:
                raise ValueError("conformance report check fields are invalid")
            checks.append(
                CheckResult(
                    name=item["name"],
                    ok=item["ok"],
                    detail=item["detail"],
                )
            )
        report = cls(
            target=payload["target"],
            checks=tuple(checks),
            profile=payload["profile"],
            report_version=payload["report_version"],
            report_schema_id=payload["$schema"],
            subject_kind=payload["subject_kind"],
            implementation_identity=payload["implementation_identity"],
            artifact_digest=payload["artifact_digest"],
        )
        if payload["ok"] is not report.ok:
            raise ValueError("conformance report aggregate status is inconsistent")
        return report

    @property
    def check_projection_digest(self) -> str:
        payload = {
            "implementation_identity": self.implementation_identity,
            "profile": self.profile,
            "report_version": self.report_version,
            "subject_kind": self.subject_kind.value,
            "checks": [check.to_dict() for check in self.checks],
        }
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return "sha256:" + sha256(encoded).hexdigest()


def conformance_report_schema() -> dict[str, Any]:
    check_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "ok", "detail"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "ok": {"type": "boolean"},
            "detail": {"type": "string"},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": CONFORMANCE_REPORT_SCHEMA_ID,
        "type": "object",
        "additionalProperties": False,
        "required": [
            "$schema",
            "report_version",
            "subject_kind",
            "implementation_identity",
            "target",
            "profile",
            "artifact_digest",
            "ok",
            "check_projection",
            "checks",
        ],
        "properties": {
            "$schema": {"const": CONFORMANCE_REPORT_SCHEMA_ID},
            "report_version": {"const": CONFORMANCE_REPORT_VERSION},
            "subject_kind": {
                "type": "string",
                "enum": [item.value for item in ConformanceSubjectKind],
            },
            "implementation_identity": {"type": "string", "minLength": 1},
            "target": {"type": "string", "minLength": 1},
            "profile": {"type": "string"},
            "artifact_digest": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "ok": {"type": "boolean"},
            "check_projection": {"type": "array", "items": check_schema},
            "checks": {"type": "array", "items": check_schema},
        },
    }
