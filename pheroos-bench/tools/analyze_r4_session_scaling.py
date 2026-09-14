"""Additive descriptive analysis of a terminal, frozen R4 Session pilot.

This tool was prepared during collection without consulting collected outcomes.
It never launches models, changes the study, or treats turns/agents as independent
worlds. The frozen validator replays the whole immutable grid once. Each policy
contrast then uses the identical R0 mapping; one deterministic representative is
checked against the frozen public exporter. All available matched policy pairs
are reported, irrespective of their outcomes. Run only after collection ends.

SQLite/authority and full model-file audits remain separate responsibilities.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path
from statistics import fmean
import sys

from pheroos_bench import r0_measurement as instrument
from pheroos_bench import r4_measurement as measurement
from pheroos_bench import r4_session_scaling as runner
from pheroos_bench import r4_tasks as tasks

METHOD = "r4_session_descriptive_analysis_v1"
POLICY_ORDER = ("private", "blackboard", "dedup_ttl", "versioned")
DISPATCHED = {"dispatched", "received", "response_rejected"}
SETTLED = {"received", "response_rejected"}
DEFINITIONS = {
    "analysis_timing": "implementation prepared during collection; exact descriptive formulas are not new confirmatory endpoints",
    "independent_unit": "four declared worlds; conditions, turns, agent identities and generation calls are not additional independent units",
    "paired_contrasts": "every available different-policy pair matched on cohort, logical N and resource regime; orientation follows private, blackboard, dedup_ttl, versioned",
    "quality": "frozen final-version task objective; current-snapshot and prefix success remain separate diagnostics",
    "logical_cost": "dispatched model calls + dispatched tool calls + recorded control operations",
    "accounting_overlap": "processing, transport, event and communication byte counters measure overlapping stages and must not be added as physical I/O",
    "failed_work": "publicly rejected actions, publicly valid but hidden-failing submissions, and all costs in terminal failed episodes are reported separately; these categories overlap",
    "larger_model": "charged medium-model calls/tokens and publication outcomes at those slots; attribution to a slot is not a causal contribution estimate",
    "repeated_inspection": "a later published valid inspection with a previously seen origin_identity; code inspection origins include the workspace digest",
    "target_repetition": "later evaluated inspect attempts with the same parsed string target, including failed targets and irrespective of workspace; not automatically wasted work",
    "reuse": "selected record IDs and origins previously selected at an earlier step; same-agent record reuse is reported separately",
    "public_valid": "valid-evidence counters mean public-valid task receipts (valid=True), including submissions that fail hidden scoring; they do not establish independently true facts",
    "duplicate_context": "repeated origin_identity within a selected context, with public-valid task-receipt duplicates separated from all task receipts",
    "stale_context": "selected receipt task_version differs from the current turn's task_version; public-valid stale task receipts are separated",
    "source_coverage": "distinct exact current source_id/version pairs among selected valid source receipts divided by the source_index in that dispatched model prompt",
    "global_source_coverage": "published current source receipts across the episode, distinct from the subset visible to any agent",
    "action_diversity": "distinct frozen semantic_action signatures for published valid actions, plus Shannon entropy in bits; public signatures do not establish program equivalence",
    "active_agents": "accepted-response, dispatched-model and published-record identities are reported separately, alongside every declared agent's allocation",
    "convergence": "first and persistently successful observed final-version prefixes; missing completion is censored/null, and persistence concerns only observed prefixes",
    "timing": "p50/p95 use linear interpolation at q*(n-1); descriptive samples within four worlds are not independent timing replications",
    "loading": "global model-load log and in-episode model.get time overlap and are reported separately without subtraction or summation",
    "gpu": "one resident checkpoint, sequential execution, logical concurrency one; adapter peak CUDA allocation is not total device memory or a replica count",
    "expected_null": "blackboard across N, and private versus blackboard at N=1, should expose equal common-prefix prompts; compare exact messages, model/seed and response content, retaining unequal run lengths",
    "unknown": "global invalidity or unresolved accounting blocks all usable paired exports; unknown or absent spend is never replaced by zero",
}
LIMITATIONS = [
    "Development pilot only; no efficacy, generalization, confirmatory, or scaling-law verdict.",
    "Only four constructed worlds, two related local checkpoints and one generation seed schedule.",
    "No multiplicity-adjusted confirmatory inference; all 56 available matched contrasts are descriptive instrument checks.",
    "Private evidence tasks at N>=8 have the declared information-allocation lower bound; this is not a model capability threshold.",
    "Logical N does not increase GPU replicas or hardware concurrency; timing remains sensitive to sequential host activity and ordering.",
    "Selected-message equality is an expected-null diagnostic, not a counterfactual ablation or proof that sharing caused success.",
    "Reuse, repeated inspection, source coverage and action diversity are descriptive proxies, not proof of relevance or waste.",
    "Larger-model slot outcomes do not isolate causal benefit from the preceding smaller-model history.",
    "Monetary cost and energy are unmeasured/null. Byte measures overlap and are not physical I/O.",
    "This tool checks frozen source hashes and raw episode consistency; independent SQLite/authority and full checkpoint-file audits remain required.",
]


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(wire(value).encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def parse(text):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "duplicate JSON key")
            value[key] = item
        return value
    return json.loads(text, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def save(path, value):
    with Path(path).open("x") as stream:
        stream.write(wire(value) + "\n")


def percentile(values, q):
    """Declared linear interpolation; null when no timings were observed."""
    if not values:
        return None
    ordered = sorted(values)
    index = q * (len(ordered) - 1)
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def distribution(values):
    return dict(n=len(values), total=sum(values), mean=fmean(values) if values else None,
                p50=percentile(values, 0.5), p95=percentile(values, 0.95),
                minimum=min(values) if values else None, maximum=max(values) if values else None)


def usage(calls):
    """Already-validated durable calls; distinguish known and unresolved states."""
    result = dict(dispatched_calls=0, settled_calls=0, abandoned_calls=0, reserved_calls=0,
                  actual_tokens=0, prompt_tokens=0, completion_tokens=0,
                  reserved_tokens=0, unknown_tokens=0, unknown_calls=0)
    for call in calls:
        state = call["state"]
        result["dispatched_calls"] += int(state in DISPATCHED)
        if state in SETTLED:
            response = parse(call["response"])
            result["settled_calls"] += 1
            result["actual_tokens"] += call["actual"]
            for key in ("prompt_tokens", "completion_tokens"):
                result[key] += response[key]
        elif state == "abandoned":
            result["abandoned_calls"] += 1
        elif state == "reserved":
            result["reserved_calls"] += 1
            result["reserved_tokens"] += call["reserved"]
        elif state == "dispatched":
            result["unknown_calls"] += 1
            result["unknown_tokens"] += call["reserved"]
    return result


def matched_pairs(config):
    groups = defaultdict(list)
    for condition in config["conditions"]:
        groups[condition["cohort"], condition["agents"], condition["regime"]].append(condition)
    pairs = []
    for key, conditions in sorted(groups.items()):
        ordered = sorted(conditions, key=lambda c: POLICY_ORDER.index(c["policy"]))
        for control, candidate in combinations(ordered, 2):
            require(control["policy"] != candidate["policy"], "duplicate declared policy condition")
            pairs.append((candidate["id"], control["id"]))
    return pairs


def mapped_export(rows, config, candidate, control, validated):
    """Exact frozen export mapping after a single whole-grid validation.

    This helper never validates a subset, accepts outside rows, or changes the
    frozen analyzer. The caller checks immutability and a public-export oracle.
    """
    paired_config = dict(method_version=instrument.METHOD, phase="instrument_check",
        arms=[control, candidate], world_ids={"r4_tasks": sorted(config["worlds"])},
        repetitions=1, cost_unit="call_units", **config["measurement"])
    metadata = dict(source_method_version=measurement.METHOD, source_phase="pilot", counts_toward_verdict=False,
        mapping=dict(measurement.MAPPING), source_summary=validated,
        source_accounting=validated["source_accounting"])
    if validated["status"] != "PILOT_COMPLETE":
        return dict(config=paired_config, records=[], report=dict(metadata,
                    method_version=instrument.METHOD, status="INVALID_ABORT", reason=validated["reason"]))
    records = [dict(record_version="r_episode_v1", phase="instrument_check", cell="r4_tasks",
        world_id=row["world_id"], repetition=0, arm=row["condition_id"],
        outcome="success" if row["success"] else "failed",
        cost=sum(row["accounting"][key] for key in ("model_calls", "tool_calls", "control_operations")),
        unknown_cost_units=row["accounting"]["unknown_calls"])
        for row in sorted(rows, key=lambda r: (r["world_id"], r["condition_id"]))
        if row["condition_id"] in (candidate, control)]
    report = dict(instrument.analyze(records, paired_config), **metadata)
    return dict(config=paired_config, records=records if report["status"] != "INVALID_ABORT" else [], report=report)


def source_coverage(prompt, memory):
    """Use public source identities actually present in this prompt."""
    public = parse(prompt[-1]["content"])["task"]
    if "source_index" not in public:
        return None
    expected = {(source["source_id"], source["version"]) for source in public["source_index"]}
    observed = set()
    for record in memory:
        artifact = record.get("artifact")
        if record["valid"] and artifact["kind"] == "source_receipt" and artifact["task_version"] == public["task_version"]:
            receipt = artifact["receipt"]
            observed.add((receipt["source_id"], receipt["version"]))
    covered = sorted(expected & observed)
    return dict(covered=len(covered), required=len(expected), fraction=len(covered) / len(expected),
                source_versions=[dict(source_id=name, version=version) for name, version in covered])


def episode_metrics(row, condition, config):
    calls = {call["id"]: call for call in row["ledger_calls"]}
    records = {record["id"]: record for record in row["records"]}
    model_calls = [call for call in calls.values() if call["action"] == "model.generate"]
    model_for_call = {call["id"]: parse(call["request"])["model_ref"] for call in model_calls}
    per_model = {model: usage([c for c in model_calls if model_for_call[c["id"]] == model])
                 for model in sorted(config["models"])}
    stages = defaultdict(Counter)
    for control in row["controls"]:
        stages[control["operation"]].update(operations=control["operations"], bytes=control["bytes"], entries=1)
    per_agent = []
    for index in range(condition["agents"]):
        agent = f"agent{index}"
        agent_steps = {r["step"] for r in records.values() if r["agent"] == agent}
        selected_calls = [c for c in model_calls if int(c["work_id"][4:]) in agent_steps]
        per_agent.append(dict(agent=agent, **usage(selected_calls),
            accepted_responses=sum(r["response"] is not None for r in records.values() if r["agent"] == agent),
            published_records=sum(r["published"] for r in records.values() if r["agent"] == agent)))
    coordination = Counter(dict.fromkeys(("selected_receipt_occurrences", "selected_foreign_occurrences",
        "reused_record_occurrences", "reused_provenance_occurrences", "same_agent_reused_record_occurrences", "selected_valid_evidence_occurrences",
        "selected_stale_receipt_occurrences", "selected_stale_evidence_occurrences",
        "within_prompt_duplicate_provenance_occurrences", "within_prompt_duplicate_evidence_occurrences",
        "inspection_target_attempt_repeats", "published_valid_inspections", "repeated_inspections_by_origin",
        "model_tokens_for_repeated_inspections"), 0))
    seen_records, seen_agent_records, seen_inspections, seen_targets, seen_origins = set(), set(), set(), set(), set()
    semantic_counts, action_counts = Counter(), Counter()
    current_sources = defaultdict(set)
    per_step, model_timings, tool_timings, peaks = [], [], [], []
    failed = Counter(dict.fromkeys(("unpublished_known_model_calls", "unpublished_known_model_tokens",
        "known_model_calls_without_tool_receipt", "known_model_tokens_without_tool_receipt",
        "publicly_rejected_actions", "model_tokens_for_publicly_rejected_actions",
        "publicly_valid_hidden_failed_submissions", "model_tokens_for_publicly_valid_hidden_failed_submissions",
        "terminal_failed_episode_actual_tokens", "terminal_failed_episode_logical_operations"), 0))
    model_attribution = {model: Counter(dict.fromkeys(("published_records", "published_valid_actions",
        "published_invalid_actions", "published_valid_submissions", "hidden_successful_submission_prefixes",
        "first_final_version_success_prefix"), 0)) for model in config["models"]}
    for record in row["records"]:
        step, agent = record["step"], record["agent"]
        generation, tool = calls.get(f"generate-{step}"), calls.get(f"evaluate-{step}")
        dispatched = generation is not None and generation["state"] in DISPATCHED
        known_tokens = generation["actual"] if generation and generation["state"] in SETTLED else None
        memory = [records[key] for key in record["selected_ids"]]
        origins, valid_origins = [], []
        for selected in memory:
            identity = selected["id"]
            coordination["selected_receipt_occurrences"] += 1
            coordination["selected_foreign_occurrences"] += int(selected["agent"] != agent)
            coordination["reused_record_occurrences"] += int(identity in seen_records)
            coordination["reused_provenance_occurrences"] += int(selected["origin_identity"] in seen_origins)
            coordination["same_agent_reused_record_occurrences"] += int((agent, identity) in seen_agent_records)
            coordination["selected_valid_evidence_occurrences"] += int(selected["valid"])
            stale = selected["task_version"] != record["task_version"]
            coordination["selected_stale_receipt_occurrences"] += int(stale)
            coordination["selected_stale_evidence_occurrences"] += int(stale and selected["valid"])
            seen_records.add(identity)
            seen_agent_records.add((agent, identity))
            origins.append(selected["origin_identity"])
            if selected["valid"]:
                valid_origins.append(selected["origin_identity"])
        seen_origins.update(origins)
        coordination["within_prompt_duplicate_provenance_occurrences"] += len(origins) - len(set(origins))
        coordination["within_prompt_duplicate_evidence_occurrences"] += len(valid_origins) - len(set(valid_origins))
        coverage = source_coverage(record["messages"], memory)
        response, evaluation = record.get("response"), record.get("evaluation")
        checked = evaluation["artifact"] if evaluation is not None else None
        if response is not None:
            model_timings.append(response["elapsed_ns"])
            if type(response.get("peak_cuda_bytes")) is int and response["peak_cuda_bytes"] >= 0:
                peaks.append(response["peak_cuda_bytes"])
            if not record["published"]:
                failed["unpublished_known_model_calls"] += 1
                failed["unpublished_known_model_tokens"] += known_tokens
            if evaluation is None:
                failed["known_model_calls_without_tool_receipt"] += 1
                failed["known_model_tokens_without_tool_receipt"] += known_tokens
        if evaluation is not None:
            tool_timings.append(evaluation["adapter_elapsed_ns"])
            action_counts[checked["action"]] += 1
            if not checked["valid"]:
                failed["publicly_rejected_actions"] += 1
                failed["model_tokens_for_publicly_rejected_actions"] += known_tokens
            if checked["action"] == "inspect":
                try:
                    action_request = parse(runner.frame(response["text"])[0])
                    target = action_request.get("target") if type(action_request) is dict else None
                except (ValueError, TypeError):
                    target = None
                if type(target) is str:
                    coordination["inspection_target_attempt_repeats"] += int(target in seen_targets)
                    seen_targets.add(target)
        attribution = model_attribution[record["model_ref"]]
        if record["published"]:
            attribution["published_records"] += 1
            attribution["published_valid_actions"] += int(record["valid"])
            attribution["published_invalid_actions"] += int(not record["valid"])
            if record["valid"]:
                signature = wire(record["semantic_action"])
                semantic_counts[signature] += 1
                if record["action"] == "inspect":
                    origin = record["origin_identity"]
                    repeated = origin in seen_inspections
                    coordination["published_valid_inspections"] += 1
                    coordination["repeated_inspections_by_origin"] += int(repeated)
                    coordination["model_tokens_for_repeated_inspections"] += known_tokens if repeated else 0
                    seen_inspections.add(origin)
                    if record["artifact"]["kind"] == "source_receipt":
                        receipt = record["artifact"]["receipt"]
                        current_sources[record["task_version"]].add((receipt["source_id"], receipt["version"]))
                elif record["action"] == "submit":
                    attribution["published_valid_submissions"] += 1
                    attribution["hidden_successful_submission_prefixes"] += int(record["prefix_success"])
                    if not record["prefix_success"]:
                        failed["publicly_valid_hidden_failed_submissions"] += 1
                        failed["model_tokens_for_publicly_valid_hidden_failed_submissions"] += known_tokens
        request = parse(generation["request"]) if generation is not None else None
        per_step.append(dict(step=step, agent=agent, task_version=record["task_version"], model_ref=record["model_ref"],
            model_dispatched=dispatched, known_model_tokens=known_tokens,
            prompt_sha256=digest(record["messages"]), seed=request["seed"] if request is not None else None,
            raw_response_text_sha256=sha256(response["text"].encode()).hexdigest() if response is not None else None,
            response_tokens={key: response[key] for key in ("prompt_tokens", "completion_tokens")} if response is not None else None,
            task_result_sha256=digest(checked) if checked is not None else None,
            selected_receipts=len(memory), selected_foreign_receipts=sum(r["agent"] != agent for r in memory),
            current_source_coverage=coverage, published=record["published"], valid_action=checked["valid"] if checked is not None else None,
            action=checked["action"] if checked is not None else None, prefix_success=record["prefix_success"],
            publication_elapsed_ns=record.get("elapsed_ns")))
    final_version = tasks.task_version(row["world_id"], config["steps"] - 1)
    final_prefixes = [s for s in per_step if s["published"] and s["task_version"] == final_version]
    successful = [s for s in final_prefixes if s["prefix_success"]]
    stable = next((s for i, s in enumerate(final_prefixes) if s["prefix_success"]
                   and all(later["prefix_success"] for later in final_prefixes[i:])), None) if row["success"] else None
    first = successful[0] if successful else None
    def milestone(item):
        if item is None:
            return None
        prefix_calls = [call for call in model_calls if int(call["work_id"][4:]) <= item["step"]]
        return dict(step=item["step"], global_turn=item["step"] + 1, model_ref=item["model_ref"],
                    publication_elapsed_ns=item["publication_elapsed_ns"], model_usage=usage(prefix_calls))
    if first is not None:
        model_attribution[first["model_ref"]]["first_final_version_success_prefix"] += 1
    total_semantics = sum(semantic_counts.values())
    entropy = -sum((count / total_semantics) * math.log2(count / total_semantics)
                   for count in semantic_counts.values()) if total_semantics else None
    covered_prompts = [s["current_source_coverage"] for s in per_step
                       if s["model_dispatched"] and s["current_source_coverage"] is not None]
    final_sources = parse(tasks.messages_for(row["world_id"], config["steps"] - 1, [])[-1]["content"])["task"].get("source_index")
    failed["terminal_failed_episode_actual_tokens"] = row["accounting"]["actual_tokens"] if not row["success"] else 0
    failed["terminal_failed_episode_logical_operations"] = sum(row["accounting"][key] for key in
        ("model_calls", "tool_calls", "control_operations")) if not row["success"] else 0
    return dict(world_id=row["world_id"], condition_id=row["condition_id"], condition=deepcopy(condition),
        status=row["status"], success=row["success"], current_snapshot_success=row["current_snapshot_success"],
        final_version_reached=row["final_version_reached"], stop_reason=row["stop_reason"],
        accounting=deepcopy(row["accounting"]), context_trim_count=row["context_trim_count"],
        control_stages={key: dict(value) for key, value in sorted(stages.items())},
        event_type_counts=dict(Counter(event["event_type"] for event in row["ledger_events"])),
        logical_operations=sum(row["accounting"][k] for k in ("model_calls", "tool_calls", "control_operations")),
        declared_agents=condition["agents"], accepted_response_agents=row["active_agents"],
        dispatched_model_agents=sum(agent["dispatched_calls"] > 0 for agent in per_agent),
        published_agents=sum(agent["published_records"] > 0 for agent in per_agent),
        per_agent=per_agent, per_model=per_model,
        model_slot_attribution={key: dict(value) for key, value in model_attribution.items()},
        failed_work=dict(failed), coordination=dict(coordination),
        action_type_counts=dict(action_counts), valid_semantic_action_counts=dict(semantic_counts),
        distinct_valid_semantic_actions=len(semantic_counts), valid_semantic_entropy_bits=entropy,
        source_coverage=dict(dispatched_source_prompts=len(covered_prompts),
            full_coverage_prompts=sum(c["covered"] == c["required"] for c in covered_prompts),
            mean_visible_fraction=fmean(c["fraction"] for c in covered_prompts) if covered_prompts else None,
            globally_inspected_by_version={str(version): [dict(source_id=name, version=v) for name, v in sorted(sources)]
                                          for version, sources in sorted(current_sources.items())},
            final_version_distinct_sources=len(current_sources[final_version]) if final_sources is not None else None,
            final_version_required_sources=len(final_sources) if final_sources is not None else None),
        convergence=dict(first_final_version_success=milestone(first), stable_observed_final_version_success=milestone(stable),
            censored=first is None, prefix_success_steps=list(row["success_steps"]),
            final_version_prefix_regressions=sum(a["prefix_success"] and not b["prefix_success"]
                                                 for a, b in zip(final_prefixes, final_prefixes[1:]))),
        timing=dict(model_generation_ns=distribution(model_timings), tool_adapter_ns=distribution(tool_timings),
                    adapter_peak_cuda_bytes_max=max(peaks) if peaks else None), steps=per_step)


def sum_counters(items):
    total = Counter()
    for item in items:
        total.update(item)
    return dict(total)


def condition_metrics(episodes, condition):
    values = [episode for episode in episodes if episode["condition_id"] == condition["id"]]
    firsts = [e["convergence"]["first_final_version_success"] for e in values]
    return dict(condition=deepcopy(condition), n_worlds=len(values), successes=sum(e["success"] for e in values),
        success_fraction=fmean(int(e["success"]) for e in values),
        current_snapshot_successes=sum(e["current_snapshot_success"] for e in values),
        final_version_reached_episodes=sum(e["final_version_reached"] for e in values),
        outcomes_by_world={e["world_id"]: dict(success=e["success"], stop_reason=e["stop_reason"],
                                             logical_operations=e["logical_operations"]) for e in values},
        accounting={key: sum(e["accounting"][key] for e in values) for key in measurement.COUNTERS},
        monetary_cost=None, logical_operations=sum(e["logical_operations"] for e in values),
        per_model={key: sum_counters(e["per_model"][key] for e in values) for key in ("small", "medium")},
        model_slot_attribution={key: sum_counters(e["model_slot_attribution"][key] for e in values) for key in ("small", "medium")},
        failed_work=sum_counters(e["failed_work"] for e in values),
        coordination=sum_counters(e["coordination"] for e in values),
        control_stages={key: sum_counters(e["control_stages"].get(key, {}) for e in values)
                        for key in sorted({key for e in values for key in e["control_stages"]})},
        event_type_counts=sum_counters(e["event_type_counts"] for e in values),
        action_diversity=dict(distinct_valid_signatures_per_world=distribution([e["distinct_valid_semantic_actions"] for e in values]),
                             entropy_bits_per_world=distribution([e["valid_semantic_entropy_bits"] for e in values
                                                                 if e["valid_semantic_entropy_bits"] is not None])),
        active_agents=dict(accepted_responses=distribution([e["accepted_response_agents"] for e in values]),
                           dispatched_models=distribution([e["dispatched_model_agents"] for e in values])),
        convergence=dict(observed_successes=sum(first is not None for first in firsts),
                         censored=sum(first is None for first in firsts),
                         successful_global_turns=distribution([first["global_turn"] for first in firsts if first is not None])),
        timing={key: distribution([e["accounting"][key] for e in values]) for key in
                ("elapsed_ns", "model_elapsed_ns", "model_load_ns", "evaluator_elapsed_ns")},
        source_prompt_coverage=dict(
            dispatched_source_prompts=sum(e["source_coverage"]["dispatched_source_prompts"] for e in values),
            full_coverage_prompts=sum(e["source_coverage"]["full_coverage_prompts"] for e in values)))


def compare_null(reference, candidate, kind):
    left = {step["step"]: step for step in reference["steps"] if step["model_dispatched"]}
    right = {step["step"]: step for step in candidate["steps"] if step["model_dispatched"]}
    compared = []
    for index in sorted(set(left) & set(right)):
        a, b = left[index], right[index]
        same_input = all(a[key] == b[key] for key in ("prompt_sha256", "model_ref", "seed"))
        have_responses = a["raw_response_text_sha256"] is not None and b["raw_response_text_sha256"] is not None
        compared.append(dict(step=index, same_prompt=a["prompt_sha256"] == b["prompt_sha256"],
            same_input=same_input, both_received=have_responses,
            same_response_text=a["raw_response_text_sha256"] == b["raw_response_text_sha256"] if have_responses else None,
            same_response_tokens=a["response_tokens"] == b["response_tokens"] if have_responses else None,
            same_task_result=a["task_result_sha256"] == b["task_result_sha256"]
                if a["task_result_sha256"] is not None and b["task_result_sha256"] is not None else None))
    return dict(kind=kind, world_id=reference["world_id"], reference=reference["condition_id"], candidate=candidate["condition_id"],
        regime=reference["condition"]["regime"], cohort=reference["condition"]["cohort"],
        reference_dispatched_steps=len(left), candidate_dispatched_steps=len(right), common_steps=len(compared),
        reference_only_steps=sorted(set(left) - set(right)), candidate_only_steps=sorted(set(right) - set(left)),
        all_common_inputs_equal=all(step["same_input"] for step in compared) if compared else None,
        first_input_divergence_step=next((s["step"] for s in compared if not s["same_input"]), None),
        first_response_divergence_on_equal_input=next((s["step"] for s in compared if s["same_input"]
                                                     and s["both_received"] and not s["same_response_text"]), None),
        reference_success=reference["success"], candidate_success=candidate["success"], steps=compared)


def expected_null_controls(episodes):
    groups = defaultdict(list)
    for episode in episodes:
        condition = episode["condition"]
        groups[episode["world_id"], condition["cohort"], condition["regime"]].append(episode)
    comparisons = []
    for _, values in sorted(groups.items()):
        blackboard = [e for e in values if e["condition"]["policy"] == "blackboard"]
        one = next((e for e in blackboard if e["declared_agents"] == 1), None)
        if one is not None:
            for other in sorted(blackboard, key=lambda e: e["declared_agents"]):
                if other is not one:
                    comparisons.append(compare_null(one, other, "blackboard_across_logical_N"))
            private = next((e for e in values if e["condition"]["policy"] == "private" and e["declared_agents"] == 1), None)
            if private is not None:
                comparisons.append(compare_null(private, one, "private_blackboard_at_N1"))
    return comparisons


def load_inputs(root):
    paths, hashes = {}, {}
    for name in ("freeze.json", "summary.json", "episodes.jsonl", "order.json", "environment.json", "model-loads.json"):
        path = root / name
        raw = path.read_bytes()
        hashes[str(path)] = sha256(raw).hexdigest()
        paths[name] = [parse(line) for line in raw.decode().splitlines() if line.strip()] if name.endswith(".jsonl") else parse(raw)
    return paths, hashes


def source_errors(inputs):
    frozen = inputs["freeze.json"]
    errors = []
    if wire(frozen["config"]) != wire(runner.configuration()):
        errors.append("frozen configuration differs from the versioned runner declaration")
    if frozen.get("counts_toward_verdict") is not False:
        errors.append("source freeze is not pilot-only")
    if Path(sys.executable).resolve() != Path(frozen["interpreter"]).resolve() or sys.version != frozen["python"]:
        errors.append("analysis must use the frozen study interpreter and Python build")
    for name, expected in frozen["source_sha256"].items():
        try:
            if sha256(Path(name).read_bytes()).hexdigest() != expected:
                errors.append(f"frozen source differs: {name}")
        except OSError as error:
            errors.append(f"frozen source unavailable: {name}: {error}")
    if inputs["summary.json"].get("status") != "PILOT_COMPLETE":
        errors.append("collection terminal summary is INVALID_ABORT")
    try:
        validate_model_loads(inputs["model-loads.json"], frozen["config"]["models"], frozen["model_manifests"])
    except ValueError as error:
        errors.append(f"invalid global model-load log: {error}")
    return errors


def validate_model_loads(loads, models, manifests):
    """Validate the exact frozen LocalModels.loads shape before any allocation."""
    require(type(loads) is list, "model-load log must be a list")
    identities = {}
    for index, entry in enumerate(loads):
        require(type(entry) is dict and set(entry) == {"model_ref", "elapsed_ns", "status", "identity", "model_class"},
                f"model-load entry {index} has an invalid shape")
        require(type(entry["model_ref"]) is str and entry["model_ref"] in models,
                f"model-load entry {index} has an undeclared model_ref")
        require(type(entry["elapsed_ns"]) is int and entry["elapsed_ns"] >= 0,
                f"model-load entry {index} elapsed_ns must be a nonnegative integer")
        require(entry["status"] == "loaded" and entry["model_class"] == "Qwen2ForCausalLM",
                f"model-load entry {index} was not a successful declared model load")
        identity, key = entry["identity"], entry["model_ref"]
        require(type(identity) is dict and wire(identity.get("model_manifest")) == wire(manifests[key]),
                f"model-load entry {index} identity differs from the frozen manifest")
        require(key not in identities or identities[key] == wire(identity),
                f"model-load entry {index} identity drifted")
        identities[key] = wire(identity)


def invalidate(result, pending_pairs, errors, reason):
    """Retain the source evidence and selected contrasts, suppress usable outputs."""
    result["status"] = "INVALID_ABORT"
    result["errors"] = list(dict.fromkeys(errors))
    for key in ("by_condition", "total_accounting", "total_successful_episodes", "model_loads"):
        result.pop(key, None)
    for _, exported in pending_pairs:
        exported["records"] = []
        exported["report"] = dict(status="INVALID_ABORT", counts_toward_verdict=False,
            reason=reason, source_validation=result.get("source_validation"),
            source_accounting=result.get("source_validation", {}).get("source_accounting"))
    result["paired_export_statuses"] = {"INVALID_ABORT": len(pending_pairs)}


def overwrite_owned(path, value):
    """Only for files in the exclusive new output directory during abort recovery."""
    with Path(path).open("w") as stream:
        stream.write(wire(value) + "\n")


def finalize(destination, result, pending_pairs, index, episodes, null_controls, manifest, errors):
    """Any finalization failure invalidates the entire selected comparison set.

    Recovery touches only this invocation's exclusive output directory. If an
    invalid replacement cannot be written, remove the owned comparison file.
    Persistent filesystem failures are retained explicitly in the return value.
    """
    if errors:
        invalidate(result, pending_pairs, errors, "invalid_whole_source")
        for item in index:
            item["status"] = "INVALID_ABORT"
    result["errors"] = list(dict.fromkeys(errors))
    try:
        (destination / "pairs").mkdir()
        for name, exported in pending_pairs:
            save(destination / name, exported)
        save(destination / "paired-index.json", index)
        if not errors and episodes is not None:
            with (destination / "episode-metrics.jsonl").open("x") as stream:
                for episode in episodes:
                    stream.write(wire(dict(episode, analysis_method=METHOD, counts_toward_verdict=False,
                        source_status="PILOT_COMPLETE", source_grid_sha256=result["source_grid_sha256"])) + "\n")
            save(destination / "expected-null-controls.json", dict(analysis_method=METHOD,
                counts_toward_verdict=False, source_status="PILOT_COMPLETE",
                source_grid_sha256=result["source_grid_sha256"], comparisons=null_controls))
        save(destination / "input-manifest.json", manifest)
        save(destination / "analysis.json", result)
        hashes = {str(path.relative_to(destination)): sha256(path.read_bytes()).hexdigest()
                  for path in sorted(destination.rglob("*")) if path.is_file()}
        save(destination / "artifact-hashes.json", hashes)
    except Exception as error:
        errors.append(f"analysis finalization failed: {type(error).__name__}: {error}")
        invalidate(result, pending_pairs, errors, "analysis_finalization_failed")
        recovery_failures = []

        def replace_or_remove(path, value):
            try:
                overwrite_owned(path, value)
            except Exception as recovery_error:
                recovery_failures.append(f"invalidation write failed for {path.name}: {type(recovery_error).__name__}: {recovery_error}")
                try:
                    path.unlink(missing_ok=True)
                except OSError as removal_error:
                    recovery_failures.append(f"owned output removal failed for {path.name}: {removal_error}")

        # Invalidate every declared pair, including files not yet written.
        for name, exported in pending_pairs:
            replace_or_remove(destination / name, exported)
        for item in index:
            item["status"] = "INVALID_ABORT"
        replace_or_remove(destination / "paired-index.json", index)
        # Previously written endpoint files must not survive a failed run.
        for name in ("episode-metrics.jsonl", "expected-null-controls.json", "artifact-hashes.json"):
            try:
                (destination / name).unlink(missing_ok=True)
            except OSError as removal_error:
                recovery_failures.append(f"owned endpoint removal failed for {name}: {removal_error}")
        replace_or_remove(destination / "input-manifest.json", manifest)
        result["finalization_recovery_failures"] = recovery_failures
        replace_or_remove(destination / "analysis.json", result)
    return result


def run(results, output):
    root, destination = Path(results).resolve(), Path(output).resolve()
    require((root / "summary.json").is_file(), "collection is not terminal; analysis must wait")
    destination.mkdir(parents=True, exist_ok=False)
    result = dict(method_version=METHOD, phase="pilot_descriptive_analysis", counts_toward_verdict=False,
                  status="INVALID_ABORT", definitions=DEFINITIONS, limitations=LIMITATIONS,
                  hardware_concurrency=1, monetary_cost=None, energy=None,
                  analysis_interpreter=sys.executable, analysis_python=sys.version)
    inputs, input_hashes, errors, pending_pairs = None, {}, [], []
    episodes, null_controls = None, None
    config = runner.configuration()
    pairs = matched_pairs(config)
    tool_hash_before = sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        inputs, input_hashes = load_inputs(root)
        rows_blob = wire(inputs["episodes.jsonl"])
        rows = parse(rows_blob)
        grid_digest = sha256(rows_blob.encode()).hexdigest()
        errors.extend(source_errors(inputs))
        declared_order = [dict(world_id=world, condition_id=condition["id"]) for world, condition in runner.execution_order(config)]
        if inputs["order.json"] != declared_order:
            errors.append("stored order differs from the frozen seeded execution order")
        if [dict(world_id=r.get("world_id"), condition_id=r.get("condition_id")) for r in rows] != declared_order:
            errors.append("episode order/grid differs from the frozen declaration")
        validated = measurement.summarize(rows, config)
        result.update(source_validation=validated, source_grid_sha256=grid_digest,
            n_worlds=len(config["worlds"]), n_conditions=len(config["conditions"]), n_episodes=len(rows),
            collection_summary_status=inputs["summary.json"].get("status"))
        if validated["status"] != "PILOT_COMPLETE":
            errors.append("frozen full-grid measurement validation failed")
        elif wire(validated) != wire(inputs["summary.json"]):
            errors.append("collection measurement summary does not reproduce from raw episodes")
        pairs = matched_pairs(config)
        if not errors:
            # Deterministic choice made from declarations, never from outcomes.
            candidate, control = pairs[0]
            local = mapped_export(rows, config, candidate, control, validated)
            oracle = measurement.export_pair(rows, config, candidate, control)
            require(wire(local) == wire(oracle), "additive mapping differs from frozen public export oracle")
            result["representative_export_oracle"] = dict(status="EXACT_MATCH", candidate=candidate, control=control)
            conditions = {condition["id"]: condition for condition in config["conditions"]}
            episodes = [episode_metrics(row, conditions[row["condition_id"]], config) for row in rows]
            null_controls = expected_null_controls(episodes)
            loads = inputs["model-loads.json"]
            result.update(by_condition=[condition_metrics(episodes, condition) for condition in config["conditions"]],
                total_accounting={key: sum(row["accounting"][key] for row in rows) for key in measurement.COUNTERS},
                total_successful_episodes=sum(row["success"] for row in rows),
                model_loads=dict(logged_load_events=len(loads),
                    logged_weight_management_ns=distribution([entry["elapsed_ns"] for entry in loads]),
                    per_model={key: distribution([entry["elapsed_ns"] for entry in loads if entry["model_ref"] == key])
                               for key in config["models"]},
                    in_episode_model_get_ns=sum(row["accounting"]["model_load_ns"] for row in rows),
                    interpretation=DEFINITIONS["loading"]), environment=inputs["environment.json"])
        else:
            result["representative_export_oracle"] = dict(status="NOT_RUN_INVALID_SOURCE")
        index = []
        for number, (candidate, control) in enumerate(pairs):
            if errors:
                exported = dict(config=None, records=[], report=dict(status="INVALID_ABORT", counts_toward_verdict=False,
                    reason="invalid_whole_source", source_validation=validated, source_accounting=validated["source_accounting"]))
            else:
                exported = mapped_export(rows, config, candidate, control, validated)
            exported["source_grid_sha256"] = grid_digest
            exported["analysis_method"] = METHOD
            name = f"pairs/{number:02d}-{candidate}-vs-{control}.json"
            pending_pairs.append((name, exported))
            index.append(dict(candidate=candidate, control=control, file=name,
                              status=exported["report"]["status"], n_worlds=len(config["worlds"])))
        require(sha256(wire(rows).encode()).hexdigest() == grid_digest, "analysis mutated the immutable source grid")
        result["paired_comparisons"] = len(pairs)
        result["paired_export_statuses"] = dict(Counter(item["status"] for item in index))
        result["status"] = "DESCRIPTIVE_PILOT_COMPLETE" if not errors else "INVALID_ABORT"
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
        result["status"] = "INVALID_ABORT"
    for path, expected in input_hashes.items():
        try:
            if sha256(Path(path).read_bytes()).hexdigest() != expected:
                errors.append(f"analysis input changed during computation: {path}")
        except OSError as error:
            errors.append(f"analysis input disappeared: {path}: {error}")
    if inputs is not None:
        try:
            errors.extend(source_errors(inputs))
        except Exception as error:
            errors.append(f"post-analysis source check failed: {type(error).__name__}: {error}")
    if sha256(Path(__file__).read_bytes()).hexdigest() != tool_hash_before:
        errors.append("analysis tool changed during computation")
    for number in range(len(pending_pairs), len(pairs)):
        candidate, control = pairs[number]
        name = f"pairs/{number:02d}-{candidate}-vs-{control}.json"
        pending_pairs.append((name, dict(config=None, records=[], report={}, source_grid_sha256=result.get("source_grid_sha256"),
                                        analysis_method=METHOD)))
    if any(exported["report"].get("status") != "VALID_MEASUREMENT" for _, exported in pending_pairs):
        errors.append("one or more paired instrument exports were invalid")
    index = [dict(candidate=candidate, control=control, file=name,
                  status=exported["report"].get("status", "INVALID_ABORT"), n_worlds=len(config["worlds"]))
             for (candidate, control), (name, exported) in zip(pairs, pending_pairs, strict=True)]
    result["paired_comparisons"] = len(pairs)
    result["paired_export_statuses"] = dict(Counter(item["status"] for item in index))
    result["analysis_tool_sha256"] = sha256(Path(__file__).read_bytes()).hexdigest()
    manifest = dict(files=input_hashes, tool_sha256=result["analysis_tool_sha256"], source_result_directory=str(root))
    return finalize(destination, result, pending_pairs, index, episodes, null_controls, manifest, errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.results, args.output)
    print(wire({key: result.get(key) for key in ("status", "n_worlds", "n_conditions", "n_episodes", "paired_comparisons", "errors")}))
    return 0 if result["status"] == "DESCRIPTIVE_PILOT_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
