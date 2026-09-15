"""Ground-truth task data extracted from the frozen visibility v1/v2 fixtures (MIT).

Host/evaluation only: renderers do not import this module. Exact function bodies
come from the source identities recorded in visibility.py and factorial.py.
"""

from pheroos_interaction.visibility import WORLDS
from pheroos_interaction.policy import _case


def source_values_v1(world_id, round_index):
    """Host-only synthetic source values. Do not send this registry to a model."""
    if world_id not in WORLDS or round_index not in (0, 1, 2):
        raise ValueError("undeclared world or round")
    if world_id not in ("shared_stable", "shared_update"):
        return {}
    updating = world_id == "shared_update"
    factor = (6 if round_index >= 1 else 3) if updating else 2
    version = 2 if updating and round_index >= 1 else 1
    return {"factor": dict(source_id="factor", source_version=version, value=factor),
            "offset": dict(source_id="offset", source_version=1, value=2 if updating else 1)}



def source_values_v2(world_id, version=2):
    """Host-only source fixtures. Values are never read by the prompt builder."""
    case, _ = _case(world_id)
    if version not in (1, 2):
        raise ValueError("undeclared source version")
    values = {("fresh_a", 1): (2, 8), ("fresh_a", 2): (4, 3),
              ("fresh_b", 1): (5, 4), ("fresh_b", 2): (3, -2)}[(case, version)]
    return {key: dict(source_id=key, source_version=version, value=value)
            for key, value in zip(("multiplier", "bias"), values)}
