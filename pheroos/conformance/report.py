from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class ConformanceReport:
    target: str
    checks: tuple[CheckResult, ...] = ()
    profile: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        payload = {"target": self.target, "ok": self.ok, "checks": [check.to_dict() for check in self.checks]}
        if self.profile:
            payload["profile"] = self.profile
        return payload
