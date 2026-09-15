"""Objective evaluation extracted unchanged from frozen visibility v1/v2 (MIT).

Never used for model-visible feedback, policy, dispatch or stopping. Source
identities are recorded in visibility.py and factorial.py.
"""

from pheroos_interaction.policy import _case


def score_v1(world_id, round_index, parsed):
    """Evaluation only; never called to choose exposure, tools, or termination."""
    if not parsed.get("valid") or parsed.get("action", {}).get("action") != "submit":
        return False
    answer = parsed["action"]["answer"]
    if world_id == "dependency_ready":
        return (type(answer) is dict and set(answer) == {"ready"} and type(answer["ready"]) is list
                and sorted(answer["ready"]) == ["delta", "gamma"])
    expected = {"simple_arithmetic": 13, "shared_stable": 7,
                "shared_update": 26 if round_index >= 1 else 14}[world_id]
    return type(answer) is int and answer == expected



def score_v2(world_id, parsed):
    """Evaluation only. Never used by selection, dispatch or stopping."""
    case, _ = _case(world_id)
    return (parsed.get("valid") is True and parsed["action"]["action"] == "submit"
            and type(parsed["action"]["answer"]) is int
            and parsed["action"]["answer"] == (23 if case == "fresh_a" else 19))

