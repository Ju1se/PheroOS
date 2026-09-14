"""Predeclared optional-sharing forks with independently metered full rollouts."""

from copy import deepcopy

from . import coordination_repair_v1_tasks as tasks
from .coordination_repair_v1 import digest, run_episode, wire


BRANCHES = ("relevant", "withheld", "irrelevant")


def prepare_prefix(parent):
    """Eligibility depends on a fixed decision prefix and public source metadata.

    It never depends on hidden success or branch outcomes. Historical artifacts
    remain in the parent; only current artifacts cross the trusted child boundary.
    """
    prefix = parent.get("captured_prefix")
    if prefix is None:
        return {"world_id": parent["world_id"], "prefix_id": "step-1", "eligible": False,
                "reason": "declared_prefix_not_reached", "prefix_tokens": 0,
                "full_parent_tokens": parent["metrics"]["tokens"] if parent.get("metrics") else None}
    public = tasks.public_world(parent["world_id"], prefix["next_step"])
    versions = {s["source_id"]: s["source_version"] for s in public["sources"]}
    current, seen = [], set()
    for item in prefix["history"]:
        value = item["value"]
        if (value["receipt_identity"] in seen
                or value["source_version"] != versions[value["source_id"]]):
            continue
        seen.add(value["receipt_identity"])
        current.append({**deepcopy(item), "baseline_readers": prefix["knowledge_readers"][value["receipt_identity"]]})
    eligible = bool(current) and any(len(item["baseline_readers"]) < parent["n"] for item in current) and prefix["remaining_steps"] > 0
    return {**prefix, "eligible": eligible,
            "reason": "current_optional_cross_agent_artifact" if eligible else "no_current_optional_cross_agent_artifact",
            "current_imports": current, "parent_prefix_hash": prefix["prefix_hash"],
            "origin_scope": parent["scope_id"],
            "full_parent_tokens": parent["metrics"]["tokens"],
            "excluded_historical_refs": [h["ref"] for h in prefix["history"] if h["ref"] not in {i["ref"] for i in current}]}


def full_rollouts(parent, *, output, model=None, campaign=None):
    """Same remaining action/token budget and seed stream; no live lease import."""
    from pathlib import Path
    from .coordination_repair_v1 import save

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    prefix = prepare_prefix(parent)
    save(output / "prefix.json", prefix)
    if not prefix["eligible"]:
        return prefix, [], []
    agents = [f"agent{i}" for i in range(parent["n"])]
    # An unrelated note is never a claimed tool fact, source, or permission.
    # Match serialized byte count as a starting point; actual tokenizer lengths
    # are measured below and residual token differences remain explicit.
    optional_bytes = len(wire([i["value"] for i in prefix["current_imports"]
                              if len(i["baseline_readers"]) < len(agents)]).encode())
    prefix_tokens = prefix["prefix_tokens"]
    remaining_cap = max(0, parent["token_cap"] - prefix_tokens)
    records, episodes = [], []
    for branch in BRANCHES:
        imports = [{**item, "readers": agents if branch == "relevant" else item["baseline_readers"]}
                   for item in prefix["current_imports"]]
        notes = ["UNRELATED NON-AUTHORITATIVE ARCHIVE LABEL: " + "circular " * (optional_bytes // 9)] if branch == "irrelevant" else []
        episode = run_episode(world=parent["world_id"], arm=parent["arm"], n=parent["n"],
            output=output / branch, model=model, campaign=campaign,
            allocation_id="fork-" + digest([parent["scope_id"], prefix["prefix_id"], branch])[:40],
            steps=prefix["remaining_steps"], token_cap=remaining_cap, seed=prefix["model_seed"],
            start_step=prefix["next_step"], imports=imports,
            prefix_feedback=prefix["private_feedback"], notes=notes,
            scheduler_offset=prefix["next_scheduler_turn"], initial_failures=prefix["failure_pressure"])
        episodes.append(episode)
        metrics = episode.get("metrics")
        record = dict(world_id=parent["world_id"], prefix_id=prefix["prefix_id"], branch=branch,
            parent_scope=parent["scope_id"], branch_scope=episode.get("scope_id"),
            prefix_hash=prefix["prefix_hash"], status=episode["status"], success=episode["success"],
            prefix_tokens=prefix_tokens, incremental_tokens=metrics["tokens"] if metrics else None,
            unknown_calls=metrics["unknown_calls"] if metrics else None,
            remaining_token_cap=remaining_cap, remaining_steps=prefix["remaining_steps"],
            invalid_actions=metrics["invalid_actions"] if metrics else None,
            first_prompt_tokens=episode["turns"][0].get("preflight_prompt_tokens") if episode.get("turns") else None,
            note_bytes=len(wire(notes).encode()), optional_artifact_bytes=optional_bytes,
            irrelevant_matching_basis="approximate serialized aggregate optional-artifact bytes; actual first-prompt token difference reported separately",
            exogenous_update_schedule="original absolute public steps",
            branch_setup_tool_calls=len(imports), complete_rollout=True,
            stop=episode.get("stop"))
        records.append(record)
    relevant_tokens = records[0]["first_prompt_tokens"]
    for record in records:
        count = record["first_prompt_tokens"]
        record["token_length_difference_from_relevant"] = count-relevant_tokens if count is not None and relevant_tokens is not None else None
    save(output / "rollout-records.json", records)
    return prefix, records, episodes
