from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from time import time
from typing import Any, Literal
from uuid import uuid4

from runtime.swarm.lifecycle import SignalLifecycleState, lifecycle_state_for_signal
from runtime.swarm.target_registry import canonical_target


class SignalType(str, Enum):
    CONSTRAINT = "constraint"
    PERMISSION = "permission"
    EVIDENCE = "evidence"
    DATA_CONTRACT = "data_contract"
    PROGRESS = "progress"
    RISK = "risk"
    NEGATIVE = "negative"
    DEMAND = "demand"
    QUORUM = "quorum"
    CAPABILITY = "capability"
    TOOL_HEALTH = "tool_health"
    MODEL_ROUTE = "model_route"
    CROWDING = "crowding"
    STOP_SIGNAL = "stop_signal"
    ENCOUNTER_RATE = "encounter_rate"
    BOTTLENECK = "bottleneck"
    AROUSAL = "arousal"
    TRUST_BADGE = "trust_badge"
    POLICING = "policing"
    CONTAMINATION = "contamination"
    QUARANTINE = "quarantine"
    LANE_ASSIGNMENT = "lane_assignment"
    HOMEOSTASIS = "homeostasis"
    MATURITY = "maturity"
    INDEPENDENCE = "independence"
    ARTIFACT_CUE = "artifact_cue"


class SignalScope(str, Enum):
    RUN = "run"
    TENANT = "tenant"
    CAPABILITY = "capability"
    AGENT = "agent"
    GLOBAL = "global"


class VerificationState(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CONTESTED = "contested"
    REJECTED = "rejected"
    BLOCKING = "blocking"


@dataclass
class PheromoneSignal:
    run_id: str
    type: SignalType | str
    target: str
    content: str
    tenant_id: str = "default"
    id: str = field(default_factory=lambda: f"sig_{uuid4().hex[:12]}")
    strength: float = 0.5
    confidence: float = 0.5
    decay_rate: float = 0.05
    priority: Literal["low", "normal", "high", "hard"] = "normal"
    scope: SignalScope | str = SignalScope.RUN
    verification_state: VerificationState | str = VerificationState.UNVERIFIED
    source_agent: str | None = None
    source_module: str | None = None
    evidence_ref: str | None = None
    blocking: bool = False
    lifecycle_state: SignalLifecycleState | str | None = None
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.type = normalize_enum(SignalType, self.type)
        self.scope = normalize_enum(SignalScope, self.scope)
        self.verification_state = normalize_enum(VerificationState, self.verification_state)
        self.target = canonical_target(self.target)
        self.strength = clamp01(self.strength)
        self.confidence = clamp01(self.confidence)
        self.decay_rate = clamp01(self.decay_rate)
        if self.priority == "hard":
            self.decay_rate = 0.0
        if self.blocking:
            self.verification_state = VerificationState.BLOCKING
        self.lifecycle_state = normalize_enum(
            SignalLifecycleState,
            self.lifecycle_state or lifecycle_state_for_signal(
                {
                    "verification_state": enum_value(self.verification_state),
                    "blocking": self.blocking,
                }
            ),
        )

    def reinforce(self, amount: float) -> None:
        self.strength = clamp01(self.strength + amount)
        self.updated_at = time()

    def penalize(self, amount: float) -> None:
        self.strength = clamp01(self.strength - amount)
        self.updated_at = time()

    def decayed_strength(self, *, now: float | None = None) -> float:
        now = now if now is not None else time()
        if self.decay_rate <= 0:
            return self.strength
        elapsed_hours = max(0.0, now - self.updated_at) / 3600
        return clamp01(self.strength * ((1 - self.decay_rate) ** elapsed_hours))

    def is_expired(self, *, now: float | None = None) -> bool:
        return self.expires_at is not None and (now if now is not None else time()) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "type": enum_value(self.type),
            "target": self.target,
            "content": self.content,
            "strength": self.strength,
            "confidence": self.confidence,
            "decay_rate": self.decay_rate,
            "priority": self.priority,
            "scope": enum_value(self.scope),
            "verification_state": enum_value(self.verification_state),
            "source_agent": self.source_agent,
            "source_module": self.source_module,
            "evidence_ref": self.evidence_ref,
            "blocking": self.blocking,
            "lifecycle_state": enum_value(self.lifecycle_state),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PheromoneSignal":
        allowed = {item.name for item in fields(cls)}
        values = {key: value for key, value in dict(payload).items() if key in allowed}
        values.setdefault("run_id", "unknown")
        values.setdefault("type", SignalType.PROGRESS)
        values.setdefault("target", "run")
        values.setdefault("content", "")
        return cls(**values)


def clamp01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return min(1.0, max(0.0, number))


def enum_value(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def normalize_enum(enum_type: type[Enum], value: Any) -> Any:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value))
    except ValueError:
        return value
