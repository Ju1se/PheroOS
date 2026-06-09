"""Swarm governance primitives for AI-as-OS agent runs."""

from runtime.swarm.contracts import signal_contract
from runtime.swarm.pheromone_field import PheromoneFieldManager
from runtime.swarm.target_registry import canonical_target
from runtime.swarm.types import (
    PheromoneSignal,
    SignalScope,
    SignalType,
    VerificationState,
)

__all__ = [
    "PheromoneFieldManager",
    "PheromoneSignal",
    "SignalScope",
    "SignalType",
    "VerificationState",
    "canonical_target",
    "signal_contract",
]
