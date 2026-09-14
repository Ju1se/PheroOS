"""Pilot-only R4 accounting and export to the unchanged paired-world instrument.

One declared task world is the independent unit. Agent counts, policy arms and
the fixed seed are conditions, never additional independent observations.
Logical call units include dispatched model/tool calls and recorded control
operations. Tokens, byte counters and diagnostic elapsed time remain separate;
local execution has no assumed monetary price. Any incomplete grid, abort or
unresolved receipt blocks the entire paired export, including otherwise valid
subsets. This module checks durable receipt consistency; it does not replace
the runtime authority, frozen source/model audit or the task evaluator.
"""
from __future__ import annotations

import json
import math
from hashlib import sha256
from statistics import fmean

from . import r0_measurement
from . import r4_tasks
from .r3_framed_pilot import frame

METHOD = "r4_session_scaling_pilot_v1"
COUNTERS = (
    "actual_tokens", "reserved_tokens", "unknown_tokens", "unknown_calls",
    "model_calls", "tool_calls", "control_operations", "processing_bytes",
    "request_bytes", "response_bytes", "event_bytes", "communication_bytes",
    "elapsed_ns", "model_elapsed_ns", "model_load_ns", "evaluator_elapsed_ns",
)
STATES = {"reserved", "dispatched", "received", "response_rejected", "abandoned"}
DISPATCHED = {"dispatched", "received", "response_rejected"}
MAPPING = {
    "world": "one independent declared world_id in cell r4_tasks",
    "repetition": "0; agent counts, conditions and the fixed seed are not independent worlds",
    "pairing": "same cohort, agent count and budget regime; different declared policies",
    "outcome": "complete success=true -> success; complete success=false -> failed",
    "call_units": "dispatched model_calls + tool_calls + control_operations; not tokens or bytes",
    "unknown": "unknown dispatches and pending reservations retain their recorded costs and block all exports",
    "phase": "pilot source -> instrument_check wire phase; no confirmatory verdict",
    "monetary_cost": "null; no local model price assumed",
    "elapsed_time": "diagnostic only; includes local scheduling and model loading effects",
    "active_agents": "agents with accepted response-bearing records; not dispatched agents on aborts",
    "model_identity": "parsed identity is constant per model_ref and manifest fields match config; exact file hashes require the freeze audit",
    "replay": "declared policy, FIFO context trims, task messages, tool results and hidden task scores replayed offline",
    "declaration": "pass the original frozen study config; runner configuration equality and freeze audit own its identity, never filter the declared grid",
}


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _text(value):
    return type(value) is str and bool(value.strip())


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate_receipt_json_key")
            result[key] = value
        return result
    _require(type(raw) is str, "receipt_json_must_be_string")
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_receipt_json")))
    _require(type(value) is dict, "receipt_json_must_be_object")
    return value


def _configuration(config):
    _require(type(config) is dict, "invalid_config")
    _require(config.get("method_version") == METHOD, "unsupported_method_version")
    _require(config.get("phase") == "pilot" and config.get("counts_toward_verdict") is False,
             "pilot_only")
    worlds = config.get("worlds")
    _require(type(worlds) is list and bool(worlds) and all(_text(x) for x in worlds)
             and len(set(worlds)) == len(worlds), "invalid_worlds")
    _require(set(worlds) <= set(r4_tasks.world_ids()), "unsupported_task_world")
    conditions = config.get("conditions")
    _require(type(conditions) is list and bool(conditions), "invalid_conditions")
    ids = set()
    for condition in conditions:
        _require(type(condition) is dict and all(_text(condition.get(k)) for k in
                 ("id", "policy", "cohort", "regime")), "invalid_condition")
        _require(condition["id"] not in ids, "duplicate_condition")
        ids.add(condition["id"])
        _require(_integer(condition.get("agents"), 1), "invalid_agents")
        _require(condition["policy"] in r4_tasks.POLICIES, "unsupported_policy")
        _require(condition["cohort"] in ("small", "medium", "mixed"), "unsupported_cohort")
        _require(condition["regime"] in ("fixed_calls", "fixed_tokens", "fixed_deadline"), "unsupported_regime")
    for key in ("steps", "max_calls", "max_new_tokens", "context_tokens"):
        _require(_integer(config.get(key), 1), f"invalid_{key}")
    _require(config["steps"] <= 32, "unsupported_step_count")
    for key in ("seed", "token_cap", "mixed_medium_start_step"):
        _require(_integer(config.get(key)), f"invalid_{key}")
    if any(c["regime"] == "fixed_tokens" for c in conditions):
        _require(_integer(config.get("binding_token_cap"), 1), "invalid_binding_token_cap")
    _require(_integer(config.get("deadline_seconds"), 1), "invalid_deadline_seconds")
    models = config.get("models")
    _require(type(models) is dict, "invalid_models")
    for key in ("small", "medium"):
        model = models.get(key)
        _require(type(model) is dict and all(_text(model.get(field)) for field in
                 ("repository", "revision", "precision", "manifest_sha256"))
                 and "quantization" in model, "invalid_model_metadata")
    measurement = config.get("measurement")
    _require(type(measurement) is dict, "invalid_measurement")
    for key in ("budget_cap", "bootstrap_resamples"):
        _require(_integer(measurement.get(key), 1), f"invalid_measurement_{key}")
    _require(_integer(measurement.get("seed")), "invalid_measurement_seed")
    confidence = measurement.get("confidence")
    _require(type(confidence) in (int, float) and math.isfinite(confidence)
             and 0 < confidence < 1, "invalid_confidence")
    return {c["id"]: c for c in conditions}


def _source_accounting(rows):
    """Preserve reported costs per source row, even when identity/receipts fail.

    These are not validated aggregates. Duplicates remain separate and absent
    or malformed counters remain absent instead of becoming zero cost.
    """
    result = []
    for index, row in enumerate(rows if type(rows) is list else []):
        item = dict(row_index=index, reported_accounting={}, ledger_actual_tokens=None,
                    ledger_unknown_calls=None, ledger_unknown_tokens=None)
        if type(row) is dict:
            item.update({k: row[k] for k in ("world_id", "condition_id", "status")
                         if type(row.get(k)) is str})
            costs = row.get("accounting")
            if type(costs) is dict:
                item["reported_accounting"] = {k: costs[k] for k in COUNTERS if _integer(costs.get(k))}
                item["monetary_cost"] = costs.get("monetary_cost")
            calls = row.get("ledger_calls")
            if type(calls) is list:
                known = [c for c in calls if type(c) is dict]
                item["ledger_actual_tokens"] = sum(c["actual"] for c in known if _integer(c.get("actual")))
                item["ledger_unknown_calls"] = sum(c.get("state") == "dispatched" for c in known)
                item["ledger_unknown_tokens"] = sum(c["reserved"] for c in known
                    if c.get("state") == "dispatched" and _integer(c.get("reserved")))
                item["ledger_partial_or_malformed"] = any(type(c) is not dict or type(c.get("state")) is not str or c["state"] not in STATES
                                                          for c in calls)
                if item["ledger_partial_or_malformed"]:
                    item["ledger_unknown_calls"] = item["ledger_unknown_tokens"] = None
        result.append(item)
    return result


def _ledger(row, config, condition):
    from .r4_session_scaling import episode_token_cap
    calls, accounting = row.get("ledger_calls"), row.get("accounting")
    _require(type(calls) is list and type(accounting) is dict, "missing_durable_accounting")
    for key in COUNTERS:
        _require(_integer(accounting.get(key)), f"invalid_accounting_{key}")
    _require("monetary_cost" in accounting and accounting["monetary_cost"] is None,
             "local_monetary_cost_must_be_null")
    totals = {k: 0 for k in ("actual_tokens", "reserved_tokens", "unknown_tokens", "unknown_calls",
                             "model_calls", "tool_calls", "request_bytes", "response_bytes", "model_elapsed_ns")}
    indexed, occupied_tokens = {}, 0
    token_cap = episode_token_cap(config, condition)
    for call in calls:
        _require(type(call) is dict and _text(call.get("id")), "invalid_ledger_call")
        _require({"id", "work_id", "version", "epoch", "action", "request", "state", "prompt", "maximum",
                  "reserved", "response", "actual", "authority"} <= set(call), "missing_ledger_field")
        _require(call["id"] not in indexed, "duplicate_ledger_call")
        _require(type(call.get("state")) is str and call["state"] in STATES, "invalid_ledger_state")
        _require(call.get("action") in ("model.generate", "tool.evaluate"), "invalid_ledger_action")
        for key in ("prompt", "maximum", "reserved"):
            _require(_integer(call.get(key)), f"invalid_ledger_{key}")
        for key in ("version", "epoch"):
            _require(_integer(call.get(key), 1), f"invalid_ledger_{key}")
        _require(_text(call.get("work_id")), "invalid_ledger_work_id")
        _require(call["reserved"] == call["prompt"] + call["maximum"], "ledger_reservation_mismatch")
        _require(occupied_tokens + call["reserved"] <= token_cap, "reservation_exceeds_episode_token_cap")
        request = _object(call.get("request"))
        _require(request.get("task_id") == call["work_id"]
                 and type(request.get("version")) is int and request["version"] == call["version"],
                 "ledger_request_identity_mismatch")
        state, response = call["state"], None
        totals["request_bytes"] += len(call["request"].encode())
        if state in DISPATCHED:
            _object(call.get("authority"))  # Shape only: authority verification belongs to the runtime audit.
            totals["model_calls" if call["action"] == "model.generate" else "tool_calls"] += 1
        if state in ("received", "response_rejected"):
            response = _object(call.get("response"))
            _require(_integer(call.get("actual")), "invalid_ledger_actual")
            for key in ("prompt_tokens", "completion_tokens"):
                _require(_integer(response.get(key)), f"invalid_response_{key}")
            _require(response["prompt_tokens"] == call["prompt"]
                     and response["completion_tokens"] <= call["maximum"]
                     and call["actual"] == response["prompt_tokens"] + response["completion_tokens"],
                     "ledger_token_components_mismatch")
            totals["actual_tokens"] += call["actual"]
            if state == "response_rejected":
                _require(response.get("response_rejected") == "response_bytes_exceeded"
                         and _integer(response.get("response_bytes")), "invalid_rejected_response")
                totals["response_bytes"] += response["response_bytes"]
                _require(row["status"] == "INVALID_ABORT", "rejected_receipt_requires_abort")
            else:
                totals["response_bytes"] += len(call["response"].encode())
                _require(_integer(response.get("adapter_elapsed_ns")), "invalid_adapter_elapsed_ns")
                if call["action"] == "model.generate":
                    _require(_integer(response.get("elapsed_ns")), "invalid_model_elapsed_ns")
                    totals["model_elapsed_ns"] += response["elapsed_ns"]
        else:
            _require(call.get("response") is None, "unsettled_call_has_response")
            if state == "abandoned":
                _require(type(call.get("actual")) is int and call["actual"] == 0, "abandoned_call_has_cost")
            else:
                _require(call.get("actual") is None, "unsettled_call_has_actual")
            if state == "reserved":
                totals["reserved_tokens"] += call["reserved"]
            elif state == "dispatched":
                totals["unknown_tokens"] += call["reserved"]
                totals["unknown_calls"] += 1
        indexed[call["id"]] = (call, request, response)
        occupied_tokens += call["actual"] if state in ("received", "response_rejected", "abandoned") else call["reserved"]
    for key, value in totals.items():
        _require(accounting[key] == value, f"accounting_{key}_mismatch")
    _require(len(calls) <= config["max_calls"], "runtime_call_cap_exceeded")
    _require(sum(totals[k] for k in ("actual_tokens", "reserved_tokens", "unknown_tokens")) <= episode_token_cap(config, condition),
             "runtime_token_cap_exceeded")
    controls = row.get("controls")
    _require(type(controls) is list, "invalid_controls")
    for control in controls:
        _require(type(control) is dict and _text(control.get("operation"))
                 and _integer(control.get("operations")) and _integer(control.get("bytes")), "invalid_control")
    _require(accounting["control_operations"] == sum(c["operations"] for c in controls),
             "control_operations_mismatch")
    _require(accounting["processing_bytes"] == sum(c["bytes"] for c in controls), "processing_bytes_mismatch")
    _require("ledger_events" in row or row["status"] == "INVALID_ABORT", "missing_ledger_events")
    if "ledger_events" in row:
        events = row["ledger_events"]
        _require(type(events) is list and all(type(e) is dict for e in events), "invalid_ledger_events")
        _require(accounting["event_bytes"] == sum(len(_wire(e).encode()) for e in events), "event_bytes_mismatch")
        dispatched = [e.get("lineage", {}).get("call_id") for e in events
                      if e.get("event_type") == "ext.session.dispatched"]
        _require(all(type(i) is str for i in dispatched) and len(dispatched) == len(set(dispatched))
                 and set(dispatched) == {key for key, (c, _, _) in indexed.items() if c["state"] in DISPATCHED},
                 "dispatch_events_mismatch")
    return indexed


def _records(row, config, condition, indexed):
    # The concrete runner owns this projection; late import avoids a cycle.
    from .r4_session_scaling import history_record
    records = row.get("records")
    _require(type(records) is list and len(records) <= config["steps"], "invalid_step_records")
    previous, used, communication, trimmed, completed, receipt_order = {}, set(), 0, 0, [], []
    for step, record in enumerate(records):
        _require(type(record) is dict and type(record.get("step")) is int and record["step"] == step
                 and record.get("id") == f"step{step}", "invalid_record_step")
        agent = f"agent{step % condition['agents']}"
        version = r4_tasks.task_version(row["world_id"], step)
        model_ref = "medium" if condition["cohort"] == "medium" or (
            condition["cohort"] == "mixed" and step >= config["mixed_medium_start_step"]) else "small"
        _require(record.get("agent") == agent and record.get("model_ref") == model_ref
                 and type(record.get("task_version")) is int and record["task_version"] == version,
                 "record_condition_or_version_mismatch")
        _require(all(type(record.get(k)) is bool for k in ("valid", "published", "prefix_success")),
                 "invalid_record_boolean")
        selected = record.get("selected_ids")
        _require(type(selected) is list and all(type(k) is str and k in previous for k in selected)
                 and len(selected) == len(set(selected)), "invalid_selected_history")
        _require(all(previous[key]["published"] for key in selected), "selected_unpublished_history")
        memory = [history_record(previous[key]) for key in selected]
        communication += sum(len(_wire(r).encode()) for r in memory if r["agent"] != agent)
        messages = record.get("messages")
        _require(type(messages) is list and all(type(m) is dict for m in messages), "invalid_record_messages")
        expected_memory = r4_tasks.select(condition["policy"],
            [history_record(r) for r in list(previous.values())[-32:] if r["published"]], agent, step, version)
        preflight = record.get("preflight")
        _require(type(preflight) is list and 1 <= len(preflight) <= len(expected_memory) + 1,
                 "invalid_context_preflight")
        for index, check in enumerate(preflight):
            expected_messages = r4_tasks.messages_for(row["world_id"], step, expected_memory)
            _require(type(check) is dict and _integer(check.get("prompt_tokens"), 1)
                     and check.get("selected_ids") == [r["id"] for r in expected_memory]
                     and check.get("messages_sha256") == sha256(_wire(expected_messages).encode()).hexdigest(),
                     "context_preflight_binding_mismatch")
            fits = check["prompt_tokens"] + config["max_new_tokens"] <= config["context_tokens"]
            if index + 1 < len(preflight):
                _require(not fits and bool(expected_memory), "unjustified_context_trim")
                expected_memory = expected_memory[1:]
                trimmed += 1
            else:
                _require(fits, "final_context_exceeds_bound")
        _require(selected == [r["id"] for r in expected_memory], "policy_selection_mismatch")
        _require(_wire(messages) == _wire(r4_tasks.messages_for(row["world_id"], step, memory)),
                 "task_context_replay_mismatch")
        ids = [key for key in (f"generate-{step}", f"evaluate-{step}") if key in indexed]
        _require(record.get("receipt_ids") == ids, "record_durable_receipt_ids_mismatch")
        used.update(ids)
        receipt_order.extend(ids)
        for key in ids:
            call, request, response = indexed[key]
            _require(call["work_id"] == f"turn{step}" and call["version"] == version,
                     "record_receipt_identity_mismatch")
            if key == f"generate-{step}":
                expected = dict(task_id=f"turn{step}", version=version, model_ref=model_ref,
                    model_identity=request.get("model_identity"), messages=messages,
                    max_new_tokens=config["max_new_tokens"],
                    seed=config["seed"] + config["worlds"].index(row["world_id"]) * 100 + step)
                _require(call["action"] == "model.generate" and type(expected["model_identity"]) is dict
                         and _wire(request) == _wire(expected), "generation_request_binding_mismatch")
                manifest = expected["model_identity"].get("model_manifest")
                _require(type(manifest) is dict and all(field in manifest and
                         _wire(manifest[field]) == _wire(config["models"][model_ref][field])
                         for field in ("repository", "revision", "precision", "quantization")),
                         "model_manifest_config_mismatch")
                _require(call["prompt"] >= 1 and call["maximum"] == config["max_new_tokens"]
                         and call["reserved"] <= config["context_tokens"], "generation_context_mismatch")
                _require(call["prompt"] == preflight[-1]["prompt_tokens"], "generation_preflight_token_mismatch")
                field = "response"
                if call["state"] == "received":
                    _require(response.get("model_ref") == model_ref and type(response.get("text")) is str,
                             "invalid_generation_response")
            else:
                _require(record.get("response") is not None, "evaluation_without_generation")
                normalized, _ = frame(record["response"].get("text"))
                expected = dict(task_id=f"turn{step}", version=version, tool_ref="task.evaluate",
                    arguments=dict(world=row["world_id"], step=step, memory=memory, text=normalized))
                _require(call["action"] == "tool.evaluate" and call["prompt"] == call["maximum"] == 0
                         and _wire(request) == _wire(expected), "evaluation_request_binding_mismatch")
                field = "evaluation"
                if call["state"] == "received":
                    _require(response.get("tool_ref") == "task.evaluate" and type(response.get("artifact")) is dict,
                             "invalid_evaluation_response")
                    replayed = r4_tasks.apply(row["world_id"], step, memory, normalized)
                    _require(_wire(response["artifact"]) == _wire(replayed), "tool_result_replay_mismatch")
            value = record.get(field)
            if value is not None or row["status"] == "complete" and call["state"] == "received":
                _require(call["state"] == "received" and _wire(value) == _wire(response),
                         f"{field}_raw_receipt_mismatch")
        for field, key in (("response", f"generate-{step}"), ("evaluation", f"evaluate-{step}")):
            _require(record.get(field) is None or key in indexed, "record_response_without_receipt")
        if record["published"]:
            receipt = record.get("evaluation")
            _require(type(receipt) is dict and type(receipt.get("artifact")) is dict,
                     "publication_without_tool_receipt")
            _require(all(k in record and _wire(record[k]) == _wire(value)
                         for k, value in receipt["artifact"].items()), "publication_receipt_mismatch")
            completed.append(history_record(record))
            _require(record["prefix_success"] is r4_tasks.score(row["world_id"], step, completed),
                     "prefix_success_replay_mismatch")
        else:
            _require(not record["valid"] and record.get("artifact") is None and not record["prefix_success"],
                     "unpublished_record_has_evidence")
        previous[record["id"]] = record
    _require(used == set(indexed), "orphan_ledger_call")
    _require(receipt_order == list(indexed), "nonsequential_durable_receipts")
    _require(row["accounting"]["communication_bytes"] == communication, "communication_bytes_mismatch")
    for key in ("context_trim_count", "active_agents", "final_step"):
        _require(_integer(row.get(key)), f"invalid_{key}")
    _require(row["context_trim_count"] == trimmed, "context_trim_count_mismatch")
    _require(row["active_agents"] == len({r["agent"] for r in records if r.get("response")}), "active_agents_mismatch")
    _require(row["final_step"] == (len(records) - 1 if records else 0), "final_step_mismatch")
    _require(type(row.get("success_steps")) is list
             and all(_integer(step) for step in row["success_steps"])
             and row["success_steps"] == [r["step"] for r in records if r["prefix_success"]], "success_steps_mismatch")
    final_version = r4_tasks.task_version(row["world_id"], config["steps"] - 1)
    _require(type(row.get("final_version_reached")) is bool and row["final_version_reached"] is
             any(r["response"] is not None and r["task_version"] == final_version for r in records),
             "final_version_reached_mismatch")
    if row["status"] == "complete":
        _require(row["success"] is r4_tasks.score(row["world_id"], config["steps"] - 1, completed),
                 "final_success_replay_mismatch")
        _require(type(row.get("current_snapshot_success")) is bool and row["current_snapshot_success"] is
                 r4_tasks.score(row["world_id"], row["final_step"], completed), "current_success_replay_mismatch")
    else:
        _require(row.get("current_snapshot_success") is None, "aborted_current_success_must_be_null")
    if row["status"] == "complete":
        _terminal_stop(row, config, condition, indexed)


def _terminal_stop(row, config, condition, indexed):
    from .r4_session_scaling import episode_token_cap
    reason, records, accounting = row.get("stop_reason"), row["records"], row["accounting"]
    _require(reason in ("call_limit", "deadline", "budget"), "invalid_complete_stop_reason")
    if reason == "call_limit":
        _require(len(records) == config["steps"] and all(r["published"] for r in records)
                 and len(indexed) == config["steps"] * 2
                 and accounting["model_calls"] == accounting["tool_calls"] == config["steps"],
                 "truncated_call_limit_episode")
    elif reason == "deadline":
        _require(condition["regime"] == "fixed_deadline"
                 and accounting["elapsed_ns"] >= config["deadline_seconds"] * 1_000_000_000,
                 "unjustified_deadline_stop")
    else:
        _require(bool(records) and not records[-1]["published"], "budget_stop_requires_partial_attempt")
        next_reservation = (records[-1]["preflight"][-1]["prompt_tokens"] + config["max_new_tokens"]
                            if f"generate-{records[-1]['step']}" not in indexed else 0)
        _require(len(indexed) >= config["max_calls"] or
                 sum(accounting[k] for k in ("actual_tokens", "reserved_tokens", "unknown_tokens"))
                 + next_reservation > episode_token_cap(config, condition), "unjustified_budget_stop")


def _validate(rows, config):
    conditions = _configuration(config)
    _require(type(rows) is list, "rows_must_be_list")
    expected = {(world, condition) for world in config["worlds"] for condition in conditions}
    observed, aborts, unresolved, identities = set(), [], [], {}
    for index, row in enumerate(rows):
        _require(type(row) is dict, "invalid_episode")
        _require(row.get("method_version") == METHOD and row.get("phase") == "pilot"
                 and row.get("counts_toward_verdict") is False, "episode_version_or_phase_mismatch")
        _require(_text(row.get("world_id")) and _text(row.get("condition_id")), "invalid_episode_identity")
        key = (row["world_id"], row["condition_id"])
        _require(key in expected, "undeclared_episode")
        _require(key not in observed, "duplicate_episode")
        observed.add(key)
        _require(row.get("status") in ("complete", "INVALID_ABORT"), "invalid_episode_status")
        _require(type(row.get("success")) is bool if row["status"] == "complete"
                 else row.get("success") is None, "invalid_episode_success")
        if row["status"] == "INVALID_ABORT":
            aborts.append(index)
            # A lost snapshot is an explicit abort, never invented zero spend.
            if row.get("accounting") is None or row.get("ledger_calls") is None:
                continue
        indexed = _ledger(row, config, conditions[row["condition_id"]])
        _records(row, config, conditions[row["condition_id"]], indexed)
        for call, request, _ in indexed.values():
            if call["action"] == "model.generate":
                model_ref, identity = request["model_ref"], _wire(request["model_identity"])
                _require(model_ref not in identities or identities[model_ref] == identity,
                         "model_identity_drift")
                identities[model_ref] = identity
        if any(c["state"] in ("dispatched", "reserved") for c, _, _ in indexed.values()):
            unresolved.append(index)
    _require(observed == expected, "incomplete_episode_grid")
    return conditions, aborts, unresolved


def summarize(rows, config):
    """Validate the whole declared grid and retain every row's known accounting."""
    base = dict(method_version=METHOD, phase="pilot", counts_toward_verdict=False,
                mapping=dict(MAPPING), source_accounting=_source_accounting(rows))
    try:
        conditions, aborts, unresolved = _validate(rows, config)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as error:
        return dict(base, status="INVALID_ABORT", reason=str(error), source_status="INVALID_SOURCE")
    base.update(expected_episodes=len(config["worlds"]) * len(conditions), n_episodes=len(rows),
                n_worlds=len(config["worlds"]),
                event_bytes_verified=all(type(row.get("ledger_events")) is list
                                         and type(row.get("accounting")) is dict for row in rows))
    if aborts or unresolved:
        return dict(base, status="INVALID_ABORT", reason="source_abort" if aborts else "unresolved_accounting",
                    source_status="INVALID_SOURCE" if aborts else "VALID_UNRESOLVED_ACCOUNTING",
                    aborted_row_indices=aborts, unresolved_row_indices=unresolved)
    totals = []
    for key, condition in sorted(conditions.items()):
        selected = [row for row in rows if row["condition_id"] == key]
        totals.append(dict(condition_id=key, condition=dict(condition), n_worlds=len(selected),
            successes=sum(row["success"] for row in selected), quality_mean=fmean(int(row["success"]) for row in selected),
            logical_operations=sum(sum(row["accounting"][k] for k in
                                       ("model_calls", "tool_calls", "control_operations")) for row in selected),
            accounting={k: sum(row["accounting"][k] for row in selected) for k in COUNTERS}, monetary_cost=None))
    return dict(base, status="PILOT_COMPLETE", source_status="VALID_COMPLETE", by_condition=totals)


def export_pair(rows, config, candidate_condition_id, control_condition_id):
    """Export one matched policy contrast only after full-grid validation."""
    source = summarize(rows, config)
    paired_config = None
    try:
        conditions = _configuration(config)
        _require(type(candidate_condition_id) is str and type(control_condition_id) is str
                 and candidate_condition_id in conditions and control_condition_id in conditions
                 and candidate_condition_id != control_condition_id, "invalid_pair_conditions")
        candidate, control = conditions[candidate_condition_id], conditions[control_condition_id]
        _require(all(candidate[k] == control[k] for k in ("agents", "cohort", "regime"))
                 and candidate["policy"] != control["policy"], "unmatched_policy_conditions")
        paired_config = dict(method_version=r0_measurement.METHOD, phase="instrument_check",
            arms=[control_condition_id, candidate_condition_id], world_ids={"r4_tasks": sorted(config["worlds"])},
            repetitions=1, cost_unit="call_units", **config["measurement"])
        _require(set(paired_config) == r0_measurement.CONFIG_FIELDS, "invalid_measurement_fields")
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return dict(config=None, records=[], report=dict(source, status="INVALID_ABORT", reason=str(error)))
    metadata = dict(source_method_version=METHOD, source_phase="pilot", counts_toward_verdict=False,
                    mapping=dict(MAPPING), source_summary=source, source_accounting=source["source_accounting"])
    if source["status"] != "PILOT_COMPLETE":
        return dict(config=paired_config, records=[], report=dict(metadata,
                    method_version=r0_measurement.METHOD, status="INVALID_ABORT", reason=source["reason"]))
    records = [dict(record_version="r_episode_v1", phase="instrument_check", cell="r4_tasks",
                    world_id=row["world_id"], repetition=0, arm=row["condition_id"],
                    outcome="success" if row["success"] else "failed",
                    cost=sum(row["accounting"][k] for k in ("model_calls", "tool_calls", "control_operations")),
                    unknown_cost_units=row["accounting"]["unknown_calls"])
               for row in sorted(rows, key=lambda row: (row["world_id"], row["condition_id"]))
               if row["condition_id"] in (candidate_condition_id, control_condition_id)]
    report = dict(r0_measurement.analyze(records, paired_config), **metadata)
    return dict(config=paired_config, records=records if report["status"] != "INVALID_ABORT" else [], report=report)
