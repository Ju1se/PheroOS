"""Independent ledger/grid counterexamples for the preparatory R4 instrument."""
from copy import deepcopy
import json
from hashlib import sha256

import pytest

from pheroos_bench import r0_measurement as r0
from pheroos_bench import r4_measurement as measurement
from pheroos_bench import r4_tasks as tasks
from pheroos_bench.r4_session_scaling import history_record


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def configuration():
    return dict(method_version=measurement.METHOD, phase="pilot", counts_toward_verdict=False,
        worlds=tasks.world_ids(), conditions=[
            dict(id="private", policy="private", agents=2, cohort="small", regime="fixed_deadline"),
            dict(id="versioned", policy="versioned", agents=2, cohort="small", regime="fixed_deadline"),
            dict(id="other-n", policy="private", agents=4, cohort="small", regime="fixed_deadline")],
        steps=32, max_calls=64, max_new_tokens=256, context_tokens=2048, token_cap=65536,
        seed=3109, mixed_medium_start_step=28, deadline_seconds=30, binding_token_cap=8192,
        models={key: dict(repository=f"fixture/{key}", revision="fixture-revision", precision="float16",
                          quantization=None, manifest_sha256="f" * 64) for key in ("small", "medium")},
        measurement=dict(confidence=0.95, bootstrap_resamples=40, seed=3141, budget_cap=10000))


def add_step(row, config, *, selected=(), text=None):
    step = len(row["records"])
    condition = next(c for c in config["conditions"] if c["id"] == row["condition_id"])
    version, world = tasks.task_version(row["world_id"], step), row["world_id"]
    model_ref = "medium" if condition["cohort"] == "medium" or (
        condition["cohort"] == "mixed" and step >= config["mixed_medium_start_step"]) else "small"
    memory = [history_record(row["records"][i]) for i in selected]
    messages = tasks.messages_for(world, step, memory)
    text = text or '{"action":"inspect","target":"missing"}'
    response = dict(text=text, prompt_tokens=30, completion_tokens=5,
                    elapsed_ns=7, adapter_elapsed_ns=11, peak_cuda_bytes=0, model_ref=model_ref)
    checked = tasks.apply(world, step, memory, text)
    evaluation = dict(artifact=checked, tool_ref="task.evaluate", prompt_tokens=0,
                      completion_tokens=0, adapter_elapsed_ns=3)
    record = dict(id=f"step{step}", step=step, agent=f"agent{step % condition['agents']}",
        task_version=version, model_ref=model_ref, selected_ids=[r["id"] for r in memory],
        messages=messages, receipt_ids=[f"generate-{step}", f"evaluate-{step}"], response=response,
        evaluation=evaluation, published=True, prefix_success=False, runtime_artifact_ref=f"fixture-{step}",
        preflight=[dict(prompt_tokens=30, selected_ids=[r["id"] for r in memory],
                        messages_sha256=sha256(wire(messages).encode()).hexdigest())])
    record.update(checked)
    row["records"].append(record)
    requests = [dict(task_id=f"turn{step}", version=version, model_ref=model_ref,
        model_identity={"model_manifest": {k: v for k, v in config["models"][model_ref].items()
                                            if k != "manifest_sha256"}}, messages=messages, max_new_tokens=256,
        seed=config["seed"] + config["worlds"].index(world) * 100 + step),
        dict(task_id=f"turn{step}", version=version, tool_ref="task.evaluate",
             arguments=dict(world=world, step=step, memory=memory, text=text))]
    for kind, request, result, prompt, maximum in zip(
        ("generate", "evaluate"), requests, (response, evaluation), (30, 0), (256, 0), strict=True
    ):
        call_id = f"{kind}-{step}"
        row["ledger_calls"].append(dict(id=call_id, work_id=f"turn{step}", version=version, epoch=1,
            action="model.generate" if kind == "generate" else "tool.evaluate", request=wire(request),
            response=wire(result), state="received", prompt=prompt, maximum=maximum,
            reserved=prompt + maximum, actual=result["prompt_tokens"] + result["completion_tokens"],
            authority=wire({"fixture": "runtime authority not claimed verified"})))
    row["controls"].append(dict(operation="fixture.processing", operations=3, bytes=12))
    recount(row)


def recount(row):
    """Independent arithmetic for fixtures; never used after corruption by default."""
    calls = row["ledger_calls"]
    records = row["records"]
    dispatched = [c for c in calls if c["state"] in ("received", "response_rejected", "dispatched")]
    row["ledger_events"] = [dict(event_type="ext.session.dispatched", lineage=dict(call_id=c["id"])) for c in dispatched]
    known_responses = [json.loads(c["response"]) for c in calls if c["state"] == "received"
                       and c["action"] == "model.generate"]
    row["accounting"] = dict(actual_tokens=sum(c["actual"] or 0 for c in calls),
        reserved_tokens=sum(c["reserved"] for c in calls if c["state"] == "reserved"),
        unknown_tokens=sum(c["reserved"] for c in calls if c["state"] == "dispatched"),
        unknown_calls=sum(c["state"] == "dispatched" for c in calls),
        model_calls=sum(c["action"] == "model.generate" for c in dispatched),
        tool_calls=sum(c["action"] == "tool.evaluate" for c in dispatched),
        control_operations=sum(c["operations"] for c in row["controls"]),
        processing_bytes=sum(c["bytes"] for c in row["controls"]),
        request_bytes=sum(len(c["request"].encode()) for c in calls),
        response_bytes=sum(json.loads(c["response"])["response_bytes"] if c["state"] == "response_rejected"
                           else len((c["response"] or "").encode()) for c in calls),
        event_bytes=sum(len(wire(e).encode()) for e in row["ledger_events"]),
        communication_bytes=sum(len(wire(history_record(records[int(key[4:])])).encode()) for record in records
            for key in record["selected_ids"] if records[int(key[4:])]["agent"] != record["agent"]),
        elapsed_ns=30_000_000_000, model_elapsed_ns=sum(r["elapsed_ns"] for r in known_responses),
        model_load_ns=2, evaluator_elapsed_ns=4, monetary_cost=None)
    row["final_step"] = len(records) - 1 if records else 0
    row["active_agents"] = len({r["agent"] for r in records if r["response"]})
    completed = []
    for record in records:
        if record["published"]:
            completed.append(history_record(record))
            record["prefix_success"] = tasks.score(row["world_id"], record["step"], completed)
    row["success_steps"] = [r["step"] for r in records if r["prefix_success"]]
    row["final_version_reached"] = any(r["response"] is not None and r["task_version"] ==
                                      tasks.task_version(row["world_id"], 31) for r in records)
    row["success"] = tasks.score(row["world_id"], 31, completed) if row["status"] == "complete" else None
    row["current_snapshot_success"] = tasks.score(row["world_id"], row["final_step"], completed) if row["status"] == "complete" else None


def fixture():
    config = configuration()
    rows = []
    for condition in config["conditions"]:
        for world in config["worlds"]:
            row = dict(method_version=measurement.METHOD, phase="pilot", counts_toward_verdict=False,
                world_id=world, condition_id=condition["id"], status="complete", success=False,
                records=[], controls=[], ledger_calls=[], context_trim_count=0,
                stop_reason="deadline", errors=[])
            add_step(row, config)
            rows.append(row)
    return rows, config


def exported(rows, config):
    return measurement.export_pair(rows, config, "versioned", "private")


def assert_invalid(rows, config, reason=None):
    result = exported(rows, config)
    assert result["records"] == []
    assert result["report"]["status"] == "INVALID_ABORT"
    if reason:
        assert result["report"]["reason"] == reason
    assert result["report"]["counts_toward_verdict"] is False
    return result


def test_exact_unchanged_instrument_schema_and_world_pairing():
    rows, config = fixture()
    # A concrete correct candidate supplies one success under the same hidden evaluator.
    rows[4].update(records=[], ledger_calls=[], controls=[])
    add_step(rows[4], config, text=wire(dict(action="submit", candidate=dict(
        code_lines=["def bounded_increment(value, increment, ceiling):", "    if value + increment > ceiling:",
                    "        return ceiling", "    return value + increment"]))))
    output = exported(rows, config)
    assert set(output["config"]) == r0.CONFIG_FIELDS
    assert all(set(row) == r0.ROW_FIELDS for row in output["records"])
    assert len(output["records"]) == 8
    assert output["report"]["n_worlds"] == 4
    assert output["report"]["quality"]["mean"] == 0.25
    assert output["report"]["status"] == "VALID_MEASUREMENT"
    assert r0.analyze(output["records"], output["config"])["status"] == "VALID_MEASUREMENT"
    assert output["report"]["source_phase"] == "pilot"
    assert output["report"]["phase"] == "instrument_check"
    assert output["report"]["counts_toward_verdict"] is False
    assert output["report"]["source_summary"]["expected_episodes"] == 12
    assert all(row["cost"] == 5 for row in output["records"])
    assert all(row["repetition"] == 0 for row in output["records"])


def test_failed_tasks_keep_every_cost_and_money_stays_unknown():
    rows, config = fixture()
    output = exported(rows, config)
    assert all(row["outcome"] == "failed" for row in output["records"])
    summary = measurement.summarize(rows, config)
    assert summary["status"] == "PILOT_COMPLETE"
    assert summary["event_bytes_verified"]
    for condition in summary["by_condition"]:
        assert condition["accounting"]["actual_tokens"] == 140
        assert condition["logical_operations"] == 20
        assert condition["monetary_cost"] is None


def test_input_order_does_not_create_new_worlds_or_change_paired_results():
    rows, config = fixture()
    forward, reverse = exported(rows, config), exported(list(reversed(rows)), config)
    assert forward["records"] == reverse["records"]
    for endpoint in ("quality", "cost", "n_worlds"):
        assert forward["report"][endpoint] == reverse["report"][endpoint]


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unexpected", "invalid_unselected"])
def test_entire_declared_grid_required_even_outside_selected_pair(mode):
    rows, config = fixture()
    if mode == "missing":
        rows.pop()
    elif mode == "duplicate":
        rows.append(deepcopy(rows[-1]))
    elif mode == "unexpected":
        rows[-1]["condition_id"] = "undeclared"
    else:
        rows[-1].update(status="INVALID_ABORT", success=None)
    output = assert_invalid(rows, config)
    assert output["report"]["source_accounting"][0]["ledger_actual_tokens"] == 35


@pytest.mark.parametrize("field", measurement.COUNTERS)
@pytest.mark.parametrize("value", [True, -1, 1.0, None])
def test_exact_nonnegative_accounting_counters(field, value):
    rows, config = fixture()
    rows[0]["accounting"][field] = value
    assert_invalid(rows, config, f"invalid_accounting_{field}")


@pytest.mark.parametrize("field", ["actual_tokens", "model_calls", "tool_calls", "unknown_tokens", "unknown_calls",
                                    "reserved_tokens", "request_bytes", "response_bytes", "model_elapsed_ns"])
def test_each_ledger_total_is_reconciled(field):
    rows, config = fixture()
    rows[0]["accounting"][field] += 1
    assert_invalid(rows, config, f"accounting_{field}_mismatch")


@pytest.mark.parametrize("field", ["control_operations", "processing_bytes", "event_bytes", "communication_bytes"])
def test_other_accounting_cannot_be_changed_independently(field):
    rows, config = fixture()
    rows[0]["accounting"][field] += 1
    assert_invalid(rows, config, f"{field}_mismatch")


@pytest.mark.parametrize("field", ["prompt", "maximum", "reserved", "actual", "epoch", "version"])
def test_boolean_ledger_counters_rejected(field):
    rows, config = fixture()
    rows[0]["ledger_calls"][0][field] = True
    assert_invalid(rows, config)


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens", "elapsed_ns", "adapter_elapsed_ns"])
def test_exact_response_counters(field):
    rows, config = fixture()
    response = json.loads(rows[0]["ledger_calls"][0]["response"])
    response[field] = True
    rows[0]["ledger_calls"][0]["response"] = wire(response)
    assert_invalid(rows, config)


def test_token_components_cannot_be_swapped_while_total_is_unchanged():
    rows, config = fixture()
    response = json.loads(rows[0]["ledger_calls"][0]["response"])
    response.update(prompt_tokens=5, completion_tokens=30)
    rows[0]["ledger_calls"][0]["response"] = wire(response)
    assert_invalid(rows, config, "ledger_token_components_mismatch")


@pytest.mark.parametrize("field,value", [("seed", 0), ("task_id", "foreign"), ("version", 2),
                                        ("model_ref", "medium"), ("max_new_tokens", 255),
                                        ("messages", [{"role": "user", "content": "foreign"}])])
def test_generation_binding_rejects_foreign_request_even_with_reconciled_bytes(field, value):
    rows, config = fixture()
    request = json.loads(rows[0]["ledger_calls"][0]["request"])
    request[field] = value
    rows[0]["ledger_calls"][0]["request"] = wire(request)
    recount(rows[0])
    assert_invalid(rows, config)


@pytest.mark.parametrize("field", ["text", "world", "step", "memory"])
def test_tool_request_is_bound_to_exact_world_step_selected_history_and_model_text(field):
    rows, config = fixture()
    request = json.loads(rows[0]["ledger_calls"][1]["request"])
    request["arguments"][field] = {"text": "{}", "world": config["worlds"][1], "step": 1, "memory": [None]}[field]
    rows[0]["ledger_calls"][1]["request"] = wire(request)
    recount(rows[0])
    assert_invalid(rows, config, "evaluation_request_binding_mismatch")


def test_record_raw_response_substitution_rejected_without_task_publication():
    rows, config = fixture()
    rows[0]["records"][0]["response"]["text"] = "{}"
    assert_invalid(rows, config, "response_raw_receipt_mismatch")


def test_checked_tool_and_publication_must_bind_to_receipt():
    rows, config = fixture()
    rows[0]["records"][0]["feedback"] = "forged successful check"
    assert_invalid(rows, config, "publication_receipt_mismatch")


def test_cross_agent_full_record_communication_is_counted():
    rows, config = fixture()
    add_step(rows[4], config, selected=(0,))
    assert measurement.summarize(rows, config)["status"] == "PILOT_COMPLETE"
    assert rows[4]["accounting"]["communication_bytes"] == len(wire(history_record(rows[4]["records"][0])).encode())


def make_unpublished(row):
    record = row["records"][0]
    record.update(published=False, valid=False, artifact=None, prefix_success=False)
    return record


def test_known_late_generation_is_valid_failure_and_fully_charged():
    rows, config = fixture()
    row = rows[0]
    record = make_unpublished(row)
    record.update(evaluation=None, receipt_ids=["generate-0"])
    row["ledger_calls"].pop()
    recount(row)
    output = exported(rows, config)
    assert output["report"]["status"] == "VALID_MEASUREMENT"
    selected = next(r for r in output["records"] if r["world_id"] == row["world_id"] and r["arm"] == "private")
    assert selected["outcome"] == "failed" and selected["cost"] == 4
    assert row["accounting"]["actual_tokens"] == 35


def test_known_late_tool_receipt_cannot_create_published_evidence():
    rows, config = fixture()
    make_unpublished(rows[0])
    assert measurement.summarize(rows, config)["status"] == "PILOT_COMPLETE"
    assert rows[0]["accounting"]["tool_calls"] == 1


def test_abandoned_reservation_before_dispatch_is_not_a_model_call():
    rows, config = fixture()
    row = rows[0]
    record = make_unpublished(row)
    record.update(response=None, evaluation=None, receipt_ids=["generate-0"])
    row["ledger_calls"].pop()
    row["ledger_calls"][0].update(state="abandoned", actual=0, response=None, authority=None)
    recount(row)
    assert measurement.summarize(rows, config)["status"] == "PILOT_COMPLETE"
    assert row["accounting"]["model_calls"] == row["accounting"]["actual_tokens"] == 0
    assert row["accounting"]["control_operations"] == 3


def test_budget_denial_with_no_durable_call_keeps_control_cost():
    rows, config = fixture()
    record = make_unpublished(rows[0])
    record.update(response=None, evaluation=None, receipt_ids=[])
    rows[0]["ledger_calls"] = []
    rows[0]["stop_reason"] = "budget"
    config["worlds"] = config["worlds"][:1]
    config["conditions"] = config["conditions"][:1]
    config["conditions"][0]["regime"] = "fixed_tokens"
    config["binding_token_cap"] = 285
    recount(rows[0])
    assert measurement.summarize(rows[:1], config)["status"] == "PILOT_COMPLETE"


@pytest.mark.parametrize("state", ["dispatched", "reserved"])
def test_zero_token_tool_unknown_or_pending_is_not_free_known_accounting(state):
    rows, config = fixture()
    row = rows[0]
    record = make_unpublished(row)
    record["evaluation"] = None
    row["ledger_calls"][1].update(state=state, actual=None, response=None)
    recount(row)
    summary = measurement.summarize(rows, config)
    assert summary["status"] == "INVALID_ABORT"
    assert summary["source_status"] == "VALID_UNRESOLVED_ACCOUNTING"
    assert row["accounting"]["unknown_tokens"] == 0
    assert row["accounting"]["actual_tokens"] == 35
    output = assert_invalid(rows, config, "unresolved_accounting")
    assert output["report"]["source_accounting"][0]["ledger_actual_tokens"] == 35


def test_invalid_episode_retains_known_and_unknown_token_receipts():
    rows, config = fixture()
    row = rows[0]
    add_step(row, config)
    record = row["records"][1]
    record.update(published=False, valid=False, artifact=None, prefix_success=False, response=None,
                  evaluation=None, receipt_ids=["generate-1"])
    row["ledger_calls"].pop()
    row["ledger_calls"][-1].update(state="dispatched", actual=None, response=None)
    row.update(status="INVALID_ABORT", success=None)
    recount(row)
    output = assert_invalid(rows, config, "source_abort")
    cost = output["report"]["source_accounting"][0]
    assert cost["ledger_actual_tokens"] == 35
    assert cost["ledger_unknown_tokens"] == 286
    assert cost["ledger_unknown_calls"] == 1
    assert cost["reported_accounting"]["model_calls"] == 2


def test_rejected_oversize_response_retains_actual_tokens_and_original_byte_count():
    rows, config = fixture()
    row = rows[0]
    record = make_unpublished(row)
    record.update(response=None, evaluation=None, receipt_ids=["generate-0"])
    row["ledger_calls"].pop()
    row["ledger_calls"][0].update(state="response_rejected", response=wire(dict(
        response_rejected="response_bytes_exceeded", response_digest="a" * 64,
        response_bytes=100000, prompt_tokens=30, completion_tokens=5)))
    row.update(status="INVALID_ABORT", success=None)
    recount(row)
    output = assert_invalid(rows, config, "source_abort")
    assert output["report"]["source_accounting"][0]["reported_accounting"]["response_bytes"] == 100000
    assert output["report"]["source_accounting"][0]["ledger_actual_tokens"] == 35


def test_lost_snapshot_has_no_invented_zero_accounting():
    rows, config = fixture()
    rows[0].update(status="INVALID_ABORT", success=None, accounting=None, ledger_calls=None)
    source = assert_invalid(rows, config, "source_abort")["report"]["source_accounting"][0]
    assert source["reported_accounting"] == {}
    assert source["ledger_actual_tokens"] is None
    assert source["ledger_unknown_calls"] is None
    assert not measurement.summarize(rows, config)["event_bytes_verified"]


@pytest.mark.parametrize("field,value", [("agents", 4), ("cohort", "medium"), ("regime", "fixed_calls"),
                                        ("policy", "private")])
def test_comparison_requires_matching_cohort_n_regime_and_different_policy(field, value):
    rows, config = fixture()
    config["conditions"][1][field] = value
    assert_invalid(rows, config, "unmatched_policy_conditions")


@pytest.mark.parametrize("field,value", [("phase", "heldout"), ("counts_toward_verdict", True),
    ("success", 0), ("success", None), ("status", "failed"), ("world_id", []), ("condition_id", True)])
def test_pilot_and_terminal_identity_are_strict(field, value):
    rows, config = fixture()
    rows[0][field] = value
    assert_invalid(rows, config)


@pytest.mark.parametrize("raw", ['{"task_id":"turn0","task_id":"foreign"}', "null", "[]", "NaN", "not json"])
def test_malformed_receipt_json_never_crashes_export(raw):
    rows, config = fixture()
    rows[0]["ledger_calls"][0]["request"] = raw
    assert_invalid(rows, config)


@pytest.mark.parametrize("mutate", [
    lambda rows: rows.append(None),
    lambda rows: rows[0].update(ledger_calls=[None]),
    lambda rows: rows[0]["ledger_calls"][0].update(state=[]),
    lambda rows: rows[0].update(records=[None]),
    lambda rows: rows[0].update(controls=[None]),
    lambda rows: rows[0].update(ledger_events=[{"event_type": "ext.session.dispatched", "lineage": None}]),
])
def test_malformed_nested_rows_remain_explicit_invalid(mutate):
    rows, config = fixture()
    mutate(rows)
    assert_invalid(rows, config)


def test_duplicate_or_missing_durable_receipts_cannot_be_hidden():
    rows, config = fixture()
    rows[0]["ledger_calls"].append(deepcopy(rows[0]["ledger_calls"][0]))
    assert_invalid(rows, config, "duplicate_ledger_call")
    rows, config = fixture()
    rows[0]["records"][0]["receipt_ids"] = ["generate-0"]
    assert_invalid(rows, config, "record_durable_receipt_ids_mismatch")


def test_complete_rows_require_raw_events_for_byte_and_dispatch_reconciliation():
    rows, config = fixture()
    del rows[0]["ledger_events"]
    assert_invalid(rows, config, "missing_ledger_events")


def test_malformed_config_and_nonlist_rows_are_robust():
    assert exported(None, None)["report"]["status"] == "INVALID_ABORT"
    rows, config = fixture()
    config["conditions"][0]["agents"] = True
    assert_invalid(rows, config)


def test_private_policy_cannot_consume_another_agents_receipt():
    rows, config = fixture()
    add_step(rows[0], config, selected=(0,))  # agent1 receives agent0 history in a private condition.
    assert_invalid(rows, config, "context_preflight_binding_mismatch")


def test_context_cannot_be_rewritten_even_when_record_and_durable_request_agree():
    rows, config = fixture()
    record, call = rows[0]["records"][0], rows[0]["ledger_calls"][0]
    record["messages"][0]["content"] += " injected task advice"
    request = json.loads(call["request"])
    request["messages"] = deepcopy(record["messages"])
    call["request"] = wire(request)
    record["preflight"][0]["messages_sha256"] = sha256(wire(record["messages"]).encode()).hexdigest()
    recount(rows[0])
    assert_invalid(rows, config, "context_preflight_binding_mismatch")


def trimmed_fixture():
    rows, config = fixture()
    row = rows[4]
    add_step(row, config)  # Final context after dropping the sole selected prior record.
    before = tasks.messages_for(row["world_id"], 1, [history_record(row["records"][0])])
    row["records"][1]["preflight"].insert(0, dict(prompt_tokens=1900, selected_ids=["step0"],
                                                messages_sha256=sha256(wire(before).encode()).hexdigest()))
    row["context_trim_count"] = 1
    return rows, config


def test_only_oldest_first_context_eviction_after_actual_overflow_is_admitted():
    rows, config = trimmed_fixture()
    assert measurement.summarize(rows, config)["status"] == "PILOT_COMPLETE"
    rows[4]["records"][1]["preflight"][0]["prompt_tokens"] = 30
    assert_invalid(rows, config, "unjustified_context_trim")


def test_prompt_preflight_and_received_usage_must_match():
    rows, config = fixture()
    rows[0]["records"][0]["preflight"][0]["prompt_tokens"] = 31
    assert_invalid(rows, config, "generation_preflight_token_mismatch")


def test_raw_tool_and_record_cannot_jointly_forge_a_public_check():
    rows, config = fixture()
    row, record = rows[0], rows[0]["records"][0]
    receipt = json.loads(row["ledger_calls"][1]["response"])
    receipt["artifact"]["feedback"] = "invented task tool result"
    record["evaluation"] = deepcopy(receipt)
    record["feedback"] = receipt["artifact"]["feedback"]
    row["ledger_calls"][1]["response"] = wire(receipt)
    recount(row)
    assert_invalid(rows, config, "tool_result_replay_mismatch")


@pytest.mark.parametrize("field,reason", [("success", "final_success_replay_mismatch"),
    ("current_snapshot_success", "current_success_replay_mismatch"),
    ("final_version_reached", "final_version_reached_mismatch")])
def test_summary_replays_outcomes_instead_of_trusting_flags(field, reason):
    rows, config = fixture()
    rows[0][field] = not rows[0][field]
    assert_invalid(rows, config, reason)


def test_prefix_success_cannot_be_fabricated_with_matching_success_steps():
    rows, config = fixture()
    rows[0]["records"][0]["prefix_success"] = True
    rows[0]["success_steps"] = [0]
    assert_invalid(rows, config, "prefix_success_replay_mismatch")


def test_earlier_version_success_is_only_a_diagnostic_for_common_final_objective():
    rows, config = fixture()
    row = rows[6]
    row.update(records=[], ledger_calls=[], controls=[])
    for step, target in enumerate(("route_policy", "route_capacity", "route_ceiling")):
        add_step(row, config, selected=tuple(range(step)), text=wire(dict(action="inspect", target=target)))
    citations = [dict(source_id=source, version=1) for source in ("route_policy", "route_capacity", "route_ceiling")]
    add_step(row, config, selected=(0, 1, 2), text=wire(dict(action="submit",
        candidate=dict(answer=dict(lane="amber", max_units=6), citations=citations))))
    assert row["current_snapshot_success"] is True
    assert row["success"] is False and row["final_version_reached"] is False
    output = exported(rows, config)
    assert output["report"]["status"] == "VALID_MEASUREMENT"
    episode = next(r for r in output["records"] if r["world_id"] == row["world_id"] and r["arm"] == "versioned")
    assert episode["outcome"] == "failed" and episode["cost"] == 20


@pytest.mark.parametrize("field,value", [("repository", "foreign/checkpoint"), ("revision", "foreign"),
                                         ("precision", "int8"), ("quantization", "int8")])
def test_raw_model_identity_must_match_declared_manifest_fields(field, value):
    rows, config = fixture()
    call = rows[0]["ledger_calls"][0]
    request = json.loads(call["request"])
    request["model_identity"]["model_manifest"][field] = value
    call["request"] = wire(request)
    recount(rows[0])
    assert_invalid(rows, config, "model_manifest_config_mismatch")


def test_entire_model_identity_is_stable_across_worlds_and_conditions():
    rows, config = fixture()
    call = rows[-1]["ledger_calls"][0]
    request = json.loads(call["request"])
    request["model_identity"]["foreign_runtime_version"] = "2"
    call["request"] = wire(request)
    recount(rows[-1])
    assert_invalid(rows, config, "model_identity_drift")


def test_raw_audit_diagnostics_are_excluded_from_context_projection():
    rows, config = fixture()
    add_step(rows[4], config, selected=(0,))
    rows[4]["records"][0]["offline_audit_note"] = "post-execution annotation"
    assert measurement.summarize(rows, config)["status"] == "PILOT_COMPLETE"


def test_real_common_session_runner_rows_pass_measurement(tmp_path):
    pytest.importorskip("pheroos_runtime.session_v1")
    from pheroos_bench import r4_session_scaling as runner
    config = runner.configuration()
    config["conditions"] = config["conditions"][:1]
    config["worlds"] = config["worlds"][:1]
    config["steps"] = 2
    class Model:
        identity = {"model_manifest": {k: v for k, v in config["models"]["small"].items()
                                        if k != "manifest_sha256"}}
        def count_tokens(self, messages):
            return 30
        def generate(self, messages, max_new_tokens, seed):
            return dict(text='{"action":"inspect","target":"missing"}', prompt_tokens=30,
                        completion_tokens=5, elapsed_ns=1, peak_cuda_bytes=0)
    class Models:
        def get(self, key):
            return Model()
    row = runner.episode(tmp_path / "fixture", config["worlds"][0], config["conditions"][0], config, Models())
    summary = measurement.summarize([row], config)
    assert summary["status"] == "PILOT_COMPLETE", summary


def test_short_prefix_cannot_masquerade_as_completed_call_limit():
    rows, config = fixture()
    rows[0]["stop_reason"] = "call_limit"
    assert_invalid(rows, config, "truncated_call_limit_episode")


@pytest.mark.parametrize("reason", ["success", "early_stop", None])
def test_undeclared_stopping_rules_are_not_admitted(reason):
    rows, config = fixture()
    rows[0]["stop_reason"] = reason
    assert_invalid(rows, config, "invalid_complete_stop_reason")


def test_deadline_stop_requires_the_declared_clock_boundary():
    rows, config = fixture()
    rows[0]["accounting"]["elapsed_ns"] = 29_999_999_999
    assert_invalid(rows, config, "unjustified_deadline_stop")


def test_fixed_call_regime_cannot_use_an_undeclared_deadline_stop():
    rows, config = fixture()
    config["conditions"][0]["regime"] = "fixed_calls"
    assert measurement.summarize(rows, config)["reason"] == "unjustified_deadline_stop"


def test_budget_stop_needs_an_unaffordable_or_call_limited_next_dispatch():
    rows, config = fixture()
    record = make_unpublished(rows[0])
    record.update(response=None, evaluation=None, receipt_ids=[])
    rows[0].update(ledger_calls=[], stop_reason="budget")
    recount(rows[0])
    assert_invalid(rows, config, "unjustified_budget_stop")


def test_selected_token_regime_applies_to_reservations_not_only_final_actual_usage():
    rows, config = fixture()
    config["worlds"] = config["worlds"][:1]
    config["conditions"] = config["conditions"][:1]
    config["conditions"][0]["regime"] = "fixed_tokens"
    config["binding_token_cap"] = 35
    config["steps"] = 1
    rows[0]["stop_reason"] = "call_limit"
    assert rows[0]["accounting"]["actual_tokens"] == 35
    # Generation still needed a 286-token reservation before its actual 35-token receipt.
    assert measurement.summarize(rows[:1], config)["reason"] == "reservation_exceeds_episode_token_cap"


def test_instrument_numeric_abort_also_suppresses_all_paired_records():
    rows, config = fixture()
    rows[0]["controls"][0]["operations"] = 10 ** 400
    recount(rows[0])
    assert measurement.summarize(rows, config)["status"] == "PILOT_COMPLETE"
    output = assert_invalid(rows, config)
    assert output["report"]["reason"].startswith("unrepresentable_measurement:")
    assert output["report"]["source_accounting"][0]["reported_accounting"]["control_operations"] == 10 ** 400
