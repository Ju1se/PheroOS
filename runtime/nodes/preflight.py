from __future__ import annotations

from typing import Any

from runtime.state import AgentState
from runtime.swarm.patroller_gate import build_patroller_report, patroller_signals
from runtime.swarm.signal_extractor import update_state_with_signals


async def patroller_gate_node(runtime: Any, state: AgentState) -> AgentState:
    """Run deterministic pre-executor PheroOS PatrollerGate checks."""

    del runtime
    report = build_patroller_report(state)
    return {
        "patroller_report": report,
        **update_state_with_signals({**state, "patroller_report": report}, patroller_signals(state, report)),
    }
