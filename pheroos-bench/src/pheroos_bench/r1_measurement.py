"""Experimental R1 pilot export to the unchanged R0 measurement contract.

An independent world is a seed, stratified by its declared deterministic case.
``call_units`` maps to logical metered stage operations, including unsuccessful
tasks and coordination overhead; it does not mean provider calls, tokens,
latency, energy, or bytes. Byte counters remain available in source accounting.
The R0 wire phase is ``instrument_check``; the source phase is always ``pilot``.
No output from this adapter counts toward a confirmatory verdict.
"""

from __future__ import annotations

import math

from . import r0_measurement


RECORD_VERSION = "r1_coordination_episode_v2"
CASES = ("no_update", "source_update", "constraint_update", "mixed")
STAGES = ("delivered", "routing", "encoding", "state_read", "state_write")
COST_FIELDS = {
    f"{stage}_{unit}" for stage in STAGES for unit in ("operations", "bytes")
} | {"total_accounted_operations", "total_accounted_bytes"}
MAPPING = {
    "cell": "case = (no_update, source_update, constraint_update, mixed)[seed % 4]",
    "world_id": "seed:<base-10 seed>",
    "repetition": "0; one episode per declared seed and arm",
    "outcome": "complete success=1 -> success; complete success=0 -> failed",
    "cost": "cost.total_accounted_operations",
    "call_units": (
        "logical metered stage operations summed across delivered, routing, "
        "encoding, state_read, state_write; not provider calls, tokens, or bytes"
    ),
    "phase": "pilot source -> instrument_check R0 wire contract",
    "invalid": "any invalid source row or incomplete full-arm grid blocks all records",
}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _integer(value, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _pair_config(config, control) -> dict:
    _require(type(config) is dict, "invalid_r1_config")
    _require(config.get("phase") == "pilot", "r1_pilot_required")
    _require(config.get("counts_toward_verdict") is False, "r1_pilot_only")
    _require(
        type(config.get("repeats", 1)) is int and config.get("repeats", 1) == 1,
        "r1_repeats_must_be_one",
    )
    seeds = config.get("pilot_seeds")
    _require(
        type(seeds) is list
        and bool(seeds)
        and all(_integer(seed) for seed in seeds)
        and len(set(seeds)) == len(seeds),
        "invalid_pilot_seeds",
    )
    arms = config.get("arms")
    _require(
        type(arms) is list
        and len(arms) >= 2
        and all(type(arm) is str and bool(arm.strip()) for arm in arms)
        and len(set(arms)) == len(arms)
        and "candidate" in arms,
        "invalid_r1_arms",
    )
    _require(
        type(control) is str and control in arms and control != "candidate",
        "invalid_control_arm",
    )
    measurement = config.get("measurement")
    _require(type(measurement) is dict, "invalid_measurement_config")
    for field in ("budget_cap", "bootstrap_resamples"):
        _require(_integer(measurement.get(field), 1), f"invalid_{field}")
    _require(_integer(measurement.get("seed")), "invalid_measurement_seed")
    confidence = measurement.get("confidence")
    _require(
        type(confidence) in (int, float)
        and 0 < confidence < 1
        and math.isfinite(confidence),
        "invalid_confidence",
    )
    worlds = {}
    for seed in sorted(seeds):
        worlds.setdefault(CASES[seed % len(CASES)], []).append(f"seed:{seed}")
    return {
        "method_version": r0_measurement.METHOD,
        "phase": "instrument_check",
        "arms": [control, "candidate"],
        "world_ids": worlds,
        "repetitions": 1,
        "cost_unit": "call_units",
        "budget_cap": measurement["budget_cap"],
        "confidence": confidence,
        "bootstrap_resamples": measurement["bootstrap_resamples"],
        "seed": measurement["seed"],
    }


def _source_accounting(rows) -> list[dict]:
    """Retain known counters even for malformed rows; never infer missing spend.

    These are reported row counters, not deduplicated episode totals. Keeping
    row indices avoids quietly combining duplicates into valid measurements.
    Missing or malformed counters are absent; unknown units stay explicit.
    """
    if type(rows) is not list:
        return []
    accounting = []
    for index, row in enumerate(rows):
        item = {"row_index": index}
        if type(row) is dict:
            for key in ("seed", "arm", "case", "status"):
                if type(row.get(key)) in (str, int):
                    item[key] = row[key]
            cost = row.get("cost")
            item["known_cost"] = (
                {
                    key: cost[key]
                    for key in sorted(COST_FIELDS)
                    if _integer(cost.get(key))
                }
                if type(cost) is dict
                else {}
            )
            unknown = row.get("unknown_cost_units")
            item["unknown_cost_units"] = unknown if _integer(unknown) else None
        else:
            item.update(known_cost={}, unknown_cost_units=None)
        accounting.append(item)
    return accounting


def _validate_grid(rows, config) -> None:
    _require(type(rows) is list, "records_must_be_list")
    expected = {(seed, arm) for seed in config["pilot_seeds"] for arm in config["arms"]}
    observed = set()
    for row in rows:
        _require(type(row) is dict, "invalid_record")
        _require(row.get("record_version") == RECORD_VERSION, "unsupported_record_version")
        _require(row.get("phase") == "pilot", "record_phase_mismatch")
        _require(row.get("counts_toward_verdict") is False, "record_pilot_only")
        _require(
            _integer(row.get("seed")) and type(row.get("arm")) is str,
            "invalid_record_identity",
        )
        key = (row["seed"], row["arm"])
        _require(key in expected, "undeclared_episode")
        _require(key not in observed, "duplicate_episode")
        observed.add(key)
        _require(row.get("case") == CASES[row["seed"] % len(CASES)], "case_seed_mismatch")
        cost = row.get("cost")
        _require(type(cost) is dict and set(cost) == COST_FIELDS, "invalid_cost_fields")
        _require(all(_integer(value) for value in cost.values()), "invalid_cost_counter")
        for unit in ("operations", "bytes"):
            _require(
                cost[f"total_accounted_{unit}"]
                == sum(cost[f"{stage}_{unit}"] for stage in STAGES),
                f"accounted_{unit}_mismatch",
            )
        unknown = row.get("unknown_cost_units")
        _require(_integer(unknown), "invalid_unknown_cost_units")
        status = row.get("status")
        _require(status in ("complete", "INVALID_ABORT"), "invalid_episode_status")
        if status == "INVALID_ABORT":
            _require(row.get("success") is None and unknown == 1, "invalid_abort_fields")
            raise ValueError("source_INVALID_ABORT")
        _require(unknown == 0, "unknown_cost")
        _require(type(row.get("success")) is int and row["success"] in (0, 1), "invalid_success")
    _require(observed == expected, "incomplete_episode_grid")


def export_pair(rows, config, control) -> dict:
    """Export candidate versus control only after validating the entire R1 grid.

    Return ``config``, ``records``, and ``report``. Config and records follow
    exact ``r_paired_world_mean_v1`` schemas, without modifying the R0 analyzer.
    Invalid input returns no records and an INVALID_ABORT report with known
    source accounting. An invalid config returns ``config=None``. Accounting
    represents reported rows, including duplicates; do not aggregate it as a
    validated episode grid. Failed completed tasks retain outcome and cost.
    """
    paired_config = None
    metadata = {
        "source_record_version": RECORD_VERSION,
        "source_phase": "pilot",
        "experimental": True,
        "counts_toward_verdict": False,
        "mapping": dict(MAPPING),
    }
    accounting = _source_accounting(rows)
    try:
        paired_config = _pair_config(config, control)
        _validate_grid(rows, config)
        records = [
            {
                "record_version": "r_episode_v1",
                "phase": "instrument_check",
                "cell": row["case"],
                "world_id": f"seed:{row['seed']}",
                "repetition": 0,
                "arm": row["arm"],
                "outcome": "success" if row["success"] else "failed",
                "cost": row["cost"]["total_accounted_operations"],
                "unknown_cost_units": 0,
            }
            for row in sorted(rows, key=lambda row: (row["case"], row["seed"], row["arm"]))
            if row["arm"] in paired_config["arms"]
        ]
        report = r0_measurement.analyze(records, paired_config)
        report.update(metadata)
        report["source_accounting"] = accounting
        # R0 also aborts on unrepresentable numerical measurements. Do not
        # expose apparently usable records after any measurement-level abort.
        if report["status"] == "INVALID_ABORT":
            records = []
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        records = []
        report = {
            "method_version": r0_measurement.METHOD,
            **metadata,
            "status": "INVALID_ABORT",
            "reason": str(exc),
            "source_accounting": accounting,
        }
    return {"config": paired_config, "records": records, "report": report}
