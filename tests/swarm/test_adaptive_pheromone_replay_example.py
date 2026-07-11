from pathlib import Path
import importlib.util


def load_replay_module():
    path = Path.cwd() / "examples/adaptive-pheromone-replay/replay.py"
    spec = importlib.util.spec_from_file_location("adaptive_pheromone_replay", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_adaptive_pheromone_replay_example_keeps_governance_authority() -> None:
    replay = load_replay_module()
    result = replay.run_replay(Path.cwd())

    assert result["protocol_id"] == "swarm.hybrid-pheromone"
    assert result["feedback_count"] == 2
    assert result["authority"] == "governance_retained"
    assert result["accepted_adjustments"] == {"pheromone_evaporation_rate": 0.2}
    assert result["layer_fallback_used"] is False
    assert result["decision"] == {
        "candidate_id": "candidate:alpha",
        "reason": "collective_consensus",
    }
    assert result["replay_reinforcement_count"] == 0
    assert len(result["replayed_feedback_ids"]) == 2
    assert "pheromone_observe" in result["replay_trace_events"]
    assert "pheromone_reinforce" not in result["replay_trace_events"]
    assert "commit" in result["replay_trace_events"]
    assert "candidate_score" in result["trace_events"]
    assert "commit" in result["trace_events"]
    assert any(
        trail["candidate_id"] == "candidate:alpha"
        and trail["subject_id"] == "route:alpha"
        and trail["kind"] == "positive"
        and trail["strength"] > 1.5
        for trail in result["reinforced"]
    )
