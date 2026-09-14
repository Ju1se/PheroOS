"""Descriptive world-weighted pilot measurements, never confirmatory evidence."""

from collections import defaultdict
from statistics import fmean

from . import r0_measurement


METHOD = "coordination_repair_nested_forks_v1"


def paired_call_export(records, *, arms, world_ids, budget_cap=10000):
    """Use unchanged R0 logical call_units: model + tool + control operations.

    Tokens and money remain separate raw fields. This export is an instrument
    check, not a relabeling of the pilot as a confirmatory experiment.
    """
    config = dict(method_version=r0_measurement.METHOD, phase="instrument_check",
                  arms=list(arms), world_ids=world_ids, repetitions=1,
                  cost_unit="call_units", budget_cap=budget_cap,
                  confidence=0.95, bootstrap_resamples=999, seed=319)
    rows = []
    for record in records:
        if record["arm"] not in arms:
            continue
        if record["status"] == "INVALID_ABORT":
            return {"status": "INVALID_ABORT", "reason": "invalid_episode_retained",
                    "config": config, "records": records, "counts_toward_verdict": False}
        metrics = record["metrics"]
        rows.append(dict(record_version="r_episode_v1", phase="instrument_check",
                         cell=record["family"], world_id=record["world_id"], repetition=0,
                         arm=record["arm"], outcome=record["outcome"],
                         cost=metrics["model_calls"] + metrics["tool_calls"] + metrics["control_operations"],
                         unknown_cost_units=metrics["unknown_calls"]))
    return {"config": config, "records": rows, "analysis": r0_measurement.analyze(rows, config),
            "cost_basis": "overlapping logical operation categories are not dollars or physical I/O",
            "counts_toward_verdict": False}


def analyze_forks(prefixes, records):
    """Average branch differences within world, then equally across worlds.

    Every predeclared eligible prefix needs all three complete branch records.
    Invalid actions and failed rollouts remain in the success denominator.
    Ineligible worlds define neither zero effects nor independent observations.
    """
    base = {"method_version": METHOD, "counts_toward_verdict": False,
            "estimand": "downstream branch success and incremental tokens, unconditional on action validity, within predeclared eligible prefixes"}
    try:
        expected, seen, lookup = set(), set(), {}
        for prefix in prefixes:
            key = prefix["world_id"], prefix["prefix_id"]
            if key in lookup or type(prefix["eligible"]) is not bool:
                raise ValueError("duplicate_or_invalid_prefix")
            lookup[key] = prefix
            if prefix["eligible"]:
                expected.update((*key, branch) for branch in ("relevant", "withheld", "irrelevant"))
        for record in records:
            key = record["world_id"], record["prefix_id"], record["branch"]
            if key not in expected or key in seen:
                raise ValueError("duplicate_or_undeclared_branch")
            seen.add(key)
            if (type(record["success"]) is not bool or type(record["incremental_tokens"]) is not int
                    or record["incremental_tokens"] < 0 or record["status"] not in {"VALID_KNOWN", "VALID_UNRESOLVED"}
                    or type(record["unknown_calls"]) is not int or record["unknown_calls"] < 0):
                raise ValueError("invalid_branch_observation")
        if seen != expected:
            raise ValueError("incomplete_branch_grid")
        if any(r["unknown_calls"] for r in records):
            return {**base, "status": "VALID_UNRESOLVED", "reason": "unknown_branch_usage",
                    "prefixes": prefixes, "records": records}
        groups = defaultdict(dict)
        for row in records:
            groups[(row["world_id"], row["prefix_id"])][row["branch"]] = row
        comparisons = {}
        for control in ("withheld", "irrelevant"):
            worlds = defaultdict(list)
            for (world, _), values in groups.items():
                treatment, baseline = values["relevant"], values[control]
                worlds[world].append({
                    "success": int(treatment["success"]) - int(baseline["success"]),
                    "incremental_tokens": treatment["incremental_tokens"] - baseline["incremental_tokens"],
                })
            per_world = {world: {metric: fmean(row[metric] for row in rows)
                                for metric in ("success", "incremental_tokens")}
                         for world, rows in sorted(worlds.items())}
            comparisons[control] = {"world_means": per_world,
                "mean_differences": {metric: fmean(row[metric] for row in per_world.values())
                                     if per_world else None
                                     for metric in ("success", "incremental_tokens")}}
        return {**base, "status": "VALID_KNOWN" if expected else "NO_ELIGIBLE_PREFIXES",
                "eligible_prefixes": sum(p["eligible"] for p in prefixes),
                "ineligible_prefixes": sum(not p["eligible"] for p in prefixes),
                "executed_branches": len(records), "independent_worlds": len({r["world_id"] for r in records}),
                "comparisons": comparisons,
                "prefix_tokens_total": sum(p["prefix_tokens"] for p in prefixes),
                "full_parent_tokens_total": sum(p.get("full_parent_tokens", p["prefix_tokens"]) for p in prefixes),
                "total_diagnostic_tokens": sum(p.get("full_parent_tokens", p["prefix_tokens"]) for p in prefixes) + sum(r["incremental_tokens"] for r in records),
                "incremental_tokens_total": sum(r["incremental_tokens"] for r in records),
                "intervals": None, "inference_limit": "constructed pilot worlds; no population or efficacy claim"}
    except (ValueError, TypeError, KeyError) as exc:
        return {**base, "status": "INVALID_ABORT", "reason": str(exc)}
