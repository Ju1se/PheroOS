"""Separate additive audit of the observed, terminally aborted R4 collection.

Valid-complete R4 audit requirements are unchanged. Known work is reconciled,
not promoted to a usable subset experiment. No inference or GPU query occurs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from pheroos.kernel import RuntimeScope
from pheroos.trace import TraceEvent
from pheroos_runtime.authority import authorize, authorize_r3
from pheroos_bench import r4_tasks as tasks
import audit_r4_session_scaling as complete
from audit_r3_session_capability import check, count, digest, equal, event, file_hash, framing, read, wire

METHOD = "r4_session_scaling_abort_audit_v1"
ABORT_INDEX = 204


def attempted_abort(output, row, condition, tokenizers, identities, score_cache):
    """Audit the actual LeaseLost branch without relabeling it complete/failed."""
    world, cid = row["world_id"], row["condition_id"]
    check((world, cid) == ("evidence_revision/ready_window", "fixed_tokens-small-private-n1"), "unexpected aborted cell")
    equal((row["status"], row["stop_reason"], row["success"], row["current_snapshot_success"]),
          ("INVALID_ABORT", "runtime_error", None, None), "aborted task must retain null outcomes")
    equal(row["errors"], [dict(type="LeaseLost", message="expired, cancelled, revoked or superseded work lease", stage="episode")], "unexpected abort error")
    directory = output / "episodes" / cid / world
    equal(read(directory / "episode.json"), row, "aborted file/JSONL mismatch")
    snapshot = read(directory / "snapshot.json")
    checkpoints = complete.read_database(directory / "session.sqlite", snapshot)
    equal(snapshot["calls"], row["ledger_calls"], "aborted durable calls differ")
    equal(snapshot["events"], row["ledger_events"], "aborted durable trace differs")
    run_id = f"r4-{world}-{cid}"
    limits = dict(token_cap=8192, max_calls=64, context_bytes=32768, artifact_bytes=32768, mailbox_bytes=4096, mailbox_messages=16)
    equal(snapshot["run"], dict(id=1, run_id=run_id, status="cancelled", generation=1, enabled=0,
          agents='["agent0"]', limits=wire(limits)), "aborted run/cancellation generation differs")
    check(len(row["records"]) == 8 and len(snapshot["calls"]) == 15 and len(snapshot["artifacts"]) == 7
          and len(snapshot["work"]) == 32, "unexpected aborted allocation")
    controls = []
    def control(operation, value=None, operations=1):
        controls.append(dict(operation=operation, operations=operations, bytes=len(wire(value).encode()) if value is not None else 0))
    control("session.create")
    trace = [event("created", "", dict(run_id=run_id, limits=limits))]
    artifacts = {a["ref"]: a for a in snapshot["artifacts"]}
    calls = {c["id"]: c for c in snapshot["calls"]}
    check(len(calls) == 15, "duplicate aborted receipt ID")
    expected_artifacts, published, used = [], [], []
    actual = incoming = outgoing = model_elapsed = prompt_checks = trims = 0
    invalid_tokens = 0
    for step, record in enumerate(row["records"]):
        work, current = f"turn{step}", complete.version(world, step)
        equal((record["id"], record["step"], record["agent"], record["task_version"], record["model_ref"]),
              (f"step{step}", step, "agent0", current, "small"), "aborted model/version/allocation differs")
        history = [complete.history(r) for r in published[-32:]]
        selected = complete.select("private", history, "agent0", step, current)
        control("policy.select", history, len(history) + 1)
        for item in selected:
            stored = complete.artifact_read(artifacts[item["runtime_artifact_ref"]])
            check(all(wire(item[k]) == wire(v) for k, v in stored["value"].items()), "aborted history lost durable provenance")
            control("artifact.read", stored)
        messages = tasks.messages_for(world, step, selected)
        control("context.encode", messages)
        preflight = []
        while True:
            prompt = len(tokenizers["small"].apply_chat_template(messages, add_generation_prompt=True, tokenize=True))
            prompt_checks += 1
            control("model.tokenize", messages)
            preflight.append(dict(prompt_tokens=prompt, messages_sha256=digest(messages), selected_ids=[r["id"] for r in selected]))
            if prompt + 256 <= 2048:
                break
            check(bool(selected), "aborted public context exceeded cap")
            selected, trims = selected[1:], trims + 1
            messages = tasks.messages_for(world, step, selected)
            control("context.trim", messages)
        equal(record["preflight"], preflight, "aborted prompt/preflight differs")
        equal(record["messages"], messages, "aborted prompt text differs")
        ids = [r["id"] for r in selected]
        equal(record["selected_ids"], ids, "aborted selected provenance differs")
        control("session.claim")
        control("session.checkpoint")
        trace.extend([event("claimed", work, dict(task_id=work, version=current, owner="agent0", epoch=1)),
                      event("checkpointed", work, dict(agent="agent0", bytes=len(wire(dict(selected_ids=ids)).encode()), generation=0))])
        scope = RuntimeScope("session-v1", run_id, work)
        normalized, diagnostic = framing(record["response"]["text"])
        equal(record["framing"], diagnostic, "aborted raw framing differs")
        requests = [(f"generate-{step}", "model.generate", dict(task_id=work, version=current, model_ref="small",
            model_identity=identities["small"], messages=messages, max_new_tokens=256,
            seed=3109 + complete.WORLDS.index(world) * 100 + step), record["response"], prompt, 256)]
        if step < 7:
            requests.append((f"evaluate-{step}", "tool.evaluate", dict(task_id=work, version=current, tool_ref="task.evaluate",
                arguments=dict(world=world, step=step, memory=selected, text=normalized)), record["evaluation"], 0, 0))
        equal(record["receipt_ids"], [r[0] for r in requests], "aborted step has orphan receipt IDs")
        for call_id, action, request, response, requested_prompt, maximum in requests:
            call = calls[call_id]
            check(response is not None, "known receipt disappeared")
            authority = (authorize_r3 if action == "model.generate" else authorize)(scope, work, current, action, request)
            charge = count(response["prompt_tokens"]) + count(response["completion_tokens"])
            check(response["prompt_tokens"] == requested_prompt and response["completion_tokens"] <= maximum, "aborted usage exceeds reservation")
            equal(call, dict(id=call_id, work_id=work, version=current, epoch=1, action=action, request=wire(request), state="received",
                            prompt=requested_prompt, maximum=maximum, reserved=requested_prompt + maximum,
                            response=wire(response), actual=charge, authority=wire(authority)), "aborted SQLite request/response/current authority differs")
            check(actual + requested_prompt + maximum <= 8192 and len(call["request"].encode()) <= 32768
                  and len(call["response"].encode()) <= 32768, "aborted bound exceeded")
            count(response["adapter_elapsed_ns"])
            trace.extend([event("reserved", work, dict(call_id=call_id, tokens=requested_prompt + maximum)),
                          event("dispatched", work, dict(call_id=call_id, authority=authority)),
                          event("received", work, dict(call_id=call_id, actual_tokens=charge, response_digest=digest(response)))])
            actual, incoming, outgoing = actual + charge, incoming + response["prompt_tokens"], outgoing + response["completion_tokens"]
            used.append(call_id)
            if action == "model.generate":
                check(response["model_ref"] == "small", "aborted model reply identity differs")
                model_elapsed += count(response["elapsed_ns"])
                count(response["peak_cuda_bytes"])
                control("model.driver", response)
                control("receipt.binding", complete.decoded_call(call))
                control("framing", dict(raw=response["text"], text=normalized, diagnostic=diagnostic), 1 + diagnostic["parse_operations"])
            else:
                result = tasks.apply(world, step, selected, normalized)
                equal(response["artifact"], result, "aborted prefix public evaluator differs")
                check(response["tool_ref"] == "task.evaluate", "aborted tool identity differs")
                control("tool.driver", response)
                control("receipt.binding", complete.decoded_call(call))
                control("tool.verify", result)
        if step < 7:
            check(record["published"] is True, "accepted prefix fact disappeared")
            result = record["evaluation"]["artifact"]
            check(all(wire(record[k]) == wire(v) for k, v in result.items()), "aborted prefix history differs from verified fact")
            if not result["valid"]:
                invalid_tokens += calls[f"generate-{step}"]["actual"]
            payload = dict(task_id=work, version=current, artifact=result, call_id=f"evaluate-{step}",
                           response_digest=digest(record["evaluation"]), scope_ref=scope.scope_ref)
            authority = authorize_r3(scope, work, current, "artifact.publish", payload)
            ref = "sha256:" + digest(payload)
            equal(record["runtime_artifact_ref"], ref, "aborted prefix publication reference differs")
            expected_artifacts.append(dict(ref=ref, work_id=work, version=current, publisher="agent0", value=wire(result),
                call_id=f"evaluate-{step}", response_digest=payload["response_digest"], authority=wire(authority)))
            trace.append(event("published", work, dict(artifact_ref=ref, call_id=f"evaluate-{step}", version=current,
                         response_digest=payload["response_digest"], authority=authority)))
            control("session.publish")
            count(record["elapsed_ns"])
            published.append(record)
        else:
            check(record["published"] is False and record["evaluation"] is None and record["valid"] is False
                  and record["artifact"] is None and record["prefix_success"] is False, "failed lease leaked a tool/final artifact")
            check("evaluate-7" not in calls, "a tool call was issued after the rejected lease")
    equal(used, list(calls), "aborted call order differs")
    equal(snapshot["artifacts"], expected_artifacts, "aborted artifact store differs")
    equal(checkpoints, [dict(agent="agent0", work_id="turn7", version=1, generation=0,
                            value=wire(dict(selected_ids=row["records"][-1]["selected_ids"])))], "cancelled checkpoint differs")
    for step, work in enumerate(snapshot["work"]):
        declaration = dict(id=f"turn{step}", version=complete.version(world, step), dependencies=[f"turn{step-1}"] if step else [],
                           agents=["agent0"], actions=["model.generate", "tool.evaluate"])
        equal(work, dict(id=f"turn{step}", version=complete.version(world, step), declaration=wire(declaration),
                        status="done" if step < 7 else "cancelled", owner=None, epoch=int(step < 8), expires=None, generation=0),
              "cancelled work/lease/current generation differs")
    trace.append(event("cancelled", "", dict(generation=1)))
    control("session.cancel")
    equal(snapshot["events"], trace, "aborted ordered lifecycle trace differs")
    control("session.snapshot")
    successes = []
    for index, record in enumerate(published):
        success = complete.score(world, record["step"], published[:index + 1], score_cache)
        equal(record["prefix_success"], success, "aborted prefix diagnostic differs")
        if success:
            successes.append(record["step"])
        control("evaluator.score")
    equal(row["controls"], controls, "aborted control-operation/byte accounting differs")
    equal(row["success_steps"], successes, "aborted success-step diagnostic differs")
    check(count(row["final_step"]) == 7 and count(row["active_agents"]) == 1 and count(row["context_trim_count"]) == trims
          and row["final_version_reached"] is False, "aborted allocation diagnostics differ")
    expected_costs = dict(actual_tokens=actual, reserved_tokens=0, unknown_tokens=0, unknown_calls=0,
        model_calls=8, tool_calls=7, request_bytes=sum(len(c["request"].encode()) for c in calls.values()),
        response_bytes=sum(len(c["response"].encode()) for c in calls.values()), event_bytes=sum(len(wire(e).encode()) for e in trace),
        communication_bytes=0, model_elapsed_ns=model_elapsed, control_operations=sum(c["operations"] for c in controls),
        processing_bytes=sum(c["bytes"] for c in controls))
    for field in complete.COUNTERS:
        count(row["accounting"][field])
    for key, value in expected_costs.items():
        check(row["accounting"][key] == value, "aborted accounting differs: " + key)
    for key in ("actual_tokens", "reserved_tokens", "unknown_tokens", "unknown_calls"):
        check(count(snapshot[key]) == expected_costs[key], "aborted snapshot total differs")
    check(count(snapshot["call_count"]) == 15 and actual == 4248 and row["accounting"]["monetary_cost"] is None, "aborted known totals differ")
    return dict(world_id=world, condition_id=cid, source_status="INVALID_ABORT", source_success=None,
        actual_tokens=actual, input_tokens=incoming, output_tokens=outgoing, model_calls={"small": 8}, model_tokens={"small": actual},
        tool_calls=7, authority_checks=22, tokenizer_checks=prompt_checks, publications=7, events=len(trace),
        public_invalid_model_tokens=invalid_tokens, settled_model_tokens_without_tool_evaluation=calls["generate-7"]["actual"],
        lease_cause=dict(recorded_exception="LeaseLost", recorded_message=row["errors"][0]["message"],
            location_supported_by_trace="after generate-7 settlement/framing and before evaluate-7 reservation",
            requested_lease_seconds=3600, requested_clock_source="time.time", episode_clock_source="time.monotonic_ns",
            episode_elapsed_ns=row["accounting"]["elapsed_ns"], final_generation_elapsed_ns=row["records"][-1]["response"]["elapsed_ns"],
            trace_event_fields=[f.name for f in fields(TraceEvent)], original_expiry_retained=False,
            final_work_expiry=snapshot["work"][7]["expires"], pre_error_cancel_revoke_or_expiry_events=0,
            exact_failed_predicate="not individually recorded", external_cause="UNDETERMINED",
            inference="Wall/monotonic discontinuity or host suspension is compatible with the evidence; neither is established."))


def audit(output, progress):
    check((output / "summary.json").is_file(), "collection is not terminal")
    paths = [output / n for n in ("freeze.json", "environment.json", "order.json", "model-loads.json", "episodes.jsonl", "summary.json")]
    paths += sorted((output / "episodes").rglob("episode.json")) + sorted((output / "episodes").rglob("snapshot.json")) + sorted((output / "episodes").rglob("session.sqlite"))
    before = {str(p.resolve()): file_hash(p) for p in paths}
    frozen, checked_files, tokenizers, model_paths, helpers = complete.frozen_inputs(output)
    summary = read(output / "summary.json")
    check(summary["status"] == "INVALID_ABORT" and summary["source_status"] == "INVALID_SOURCE"
          and summary["reason"] == "source_abort" and summary["counts_toward_verdict"] is False, "abort gate changed")
    check("by_condition" not in summary, "usable subset summary appeared despite full-grid abort")
    with (output / "episodes.jsonl").open() as stream:
        rows = [json.loads(line, object_pairs_hook=helpers.base._object, parse_constant=helpers.base._nonfinite) for line in stream]
    order = complete.declared_order(frozen["config"])
    equal(read(output / "order.json"), order, "frozen order differs")
    equal([dict(world_id=r["world_id"], condition_id=r["condition_id"]) for r in rows], order, "declared full grid differs")
    equal(summary["aborted_row_indices"], list(range(204, 264)), "abort/placeholder identities differ")
    equal(summary["unresolved_row_indices"], [], "unexpected unresolved source accounting")
    equal(summary["collection_abort"], dict(type="EpisodeAborted", world_id=rows[204]["world_id"], condition_id=rows[204]["condition_id"]), "collection abort identity differs")
    identities, loads = {}, read(output / "model-loads.json")
    for load in loads:
        check(load["status"] == "loaded" and load["model_class"] == "Qwen2ForCausalLM", "unexpected model loading failure/class")
        count(load["elapsed_ns"])
        key, identity = load["model_ref"], load["identity"]
        equal(identity["model_manifest"], frozen["model_manifests"][key], "loaded model manifest differs")
        for field, value in (("dtype", "float16"), ("python", frozen["python"]), ("torch", frozen["packages"]["torch"]),
                             ("transformers", frozen["packages"]["transformers"])):
            equal(identity[field], value, "loaded environment differs")
        if key in identities:
            equal(identity, identities[key], "loaded model drift")
        identities[key] = identity
    check(set(identities) == {"small", "medium"}, "missing model control")
    for key in ("cuda", "gpu", "dtype", "python", "torch", "transformers"):
        equal(identities["small"][key], identities["medium"][key], "common environment changed")
    conditions = {c["id"]: c for c in frozen["config"]["conditions"]}
    checks, score_cache, expected_loads, resident = [], {}, [], None
    for index, row in enumerate(rows):
        check(row["method_version"] == complete.METHOD and row["phase"] == "pilot" and row["counts_toward_verdict"] is False,
              "row pilot metadata differs")
        if index > ABORT_INDEX:
            equal(row, dict(method_version=complete.METHOD, phase="pilot", counts_toward_verdict=False,
                world_id=order[index]["world_id"], condition_id=order[index]["condition_id"], status="INVALID_ABORT", success=None,
                stop_reason="not_started", accounting=None, ledger_calls=None, ledger_events=None, records=[], controls=[],
                errors=[summary["collection_abort"]]), "unstarted row fabricated outcomes/accounting")
            check(not (output / "episodes" / row["condition_id"] / row["world_id"]).exists(), "unstarted cell has unreported state")
            continue
        condition = conditions[row["condition_id"]]
        requests = ([(complete.model_for(condition, 0), False)] if condition["cohort"] != "mixed" else [])
        requests += [(complete.model_for(condition, r["step"]), True) for r in row["records"]]
        within_load_ns = 0
        for key, within in requests:
            if key != resident:
                load = loads[len(expected_loads)]
                check(load["model_ref"] == key, "actual resident-model schedule differs")
                if within:
                    within_load_ns += load["elapsed_ns"]
                expected_loads.append(key)
                resident = key
        checked = (complete.audit_episode(output, row, condition, tokenizers, identities, score_cache) if index < ABORT_INDEX else
                   attempted_abort(output, row, condition, tokenizers, identities, score_cache))
        check(row["accounting"]["model_load_ns"] >= within_load_ns, "within-episode checkpoint loading cost disappeared")
        checked["source_row_index"] = index
        checks.append(checked)
        with progress.open("a") as stream:
            stream.write(wire(checked) + "\n")
        print("audited", index + 1, "/ 205 attempted; source remains INVALID_ABORT", flush=True)
    equal([load["model_ref"] for load in loads], expected_loads, "model load count/order differs")
    retained = []
    for index, row in enumerate(rows):
        item = dict(row_index=index, world_id=row["world_id"], condition_id=row["condition_id"], status=row["status"],
                    reported_accounting={}, ledger_actual_tokens=None, ledger_unknown_calls=None, ledger_unknown_tokens=None)
        if row["accounting"] is not None:
            item.update(reported_accounting={k: row["accounting"][k] for k in complete.COUNTERS}, monetary_cost=None,
                        ledger_actual_tokens=sum(c["actual"] for c in row["ledger_calls"]), ledger_unknown_calls=0,
                        ledger_unknown_tokens=0, ledger_partial_or_malformed=False)
        retained.append(item)
    equal(summary["source_accounting"], retained, "full-grid retained accounting differs")
    for field, value in dict(expected_episodes=264, n_episodes=264, n_worlds=4, event_bytes_verified=False,
                            method_version=complete.METHOD, phase="pilot").items():
        equal(summary[field], value, "aborted summary metadata differs")
    equal({str(p.resolve()): file_hash(p) for p in paths}, before, "audit changed original collection evidence")
    accounting = {k: sum(r["accounting"][k] for r in rows[:205]) for k in complete.COUNTERS}
    clocks = {}
    for index in (203, 204):
        directory = output / "episodes" / rows[index]["condition_id"] / rows[index]["world_id"]
        clocks[str(index)] = {name: dict(mtime_ns=(directory / name).stat().st_mtime_ns,
            mtime_utc=datetime.fromtimestamp((directory / name).stat().st_mtime, timezone.utc).isoformat())
            for name in ("session.sqlite", "snapshot.json", "episode.json")}
    return dict(audit_method=METHOD, audit_status="ACCOUNTING_AND_ABORT_INTEGRITY_PASS", source_status="INVALID_ABORT",
        inference_status="FULL_GRID_INVALID_NO_USABLE_PAIRED_EXPORT", counts_toward_verdict=False, generated_model_calls=0,
        created_utc=datetime.now(timezone.utc).isoformat(), original_evidence_unchanged=True,
        declared_episodes=264, completed_episodes=204, attempted_aborted_episodes=1, unstarted_episodes=59,
        completed_by_stop=dict(Counter(r["stop_reason"] for r in rows[:204])), known_attempted_accounting=accounting,
        input_tokens=sum(r["input_tokens"] for r in checks), output_tokens=sum(r["output_tokens"] for r in checks),
        known_model_tokens={key: sum(r["model_tokens"].get(key, 0) for r in checks) for key in complete.MODELS},
        authority_checks=sum(r["authority_checks"] for r in checks), tokenizer_checks=sum(r["tokenizer_checks"] for r in checks),
        publications=sum(r["publications"] for r in checks), causal_events=sum(r["events"] for r in checks),
        unique_hidden_score_replays=len(score_cache), aborted_episode=checks[-1], episode_checks=checks,
        filesystem_timing_observations=clocks, filesystem_timing_limitation="File mtimes are wall-clock observations, not recorded lease or suspend events.",
        frozen_files_checked=len(checked_files), checked_input_sha256=checked_files, evidence_sha256=before,
        source_config=frozen["config"], model_paths=model_paths, model_identities=identities, model_loads=len(loads),
        model_load_elapsed_ns=sum(load["elapsed_ns"] for load in loads), retained_source_accounting=retained,
        audit_source_sha256={str(Path(p).resolve()): file_hash(p) for p in (__file__, complete.__file__, helpers.__file__)},
        limitations=["No usable subset efficacy export despite the complete fixed-call block.",
          "59 unstarted cells have null accounting; they are not zero-cost failures.",
          "The 4248-token invalid episode is retained, including 554 tokens in its last unevaluated model receipt.",
          "The last lease expiry and contemporaneous clock values were not recorded; host suspension or a clock jump is not established.",
          "Completion-token IDs were not stored; counts reconcile to durable receipts and the frozen tensor-length implementation.",
          "No new GPU/inference work, retries, source changes, phase promotion or R4 completion verdict."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    check(not args.audit_output.exists(), "exclusive additive audit path required")
    progress = args.audit_output.with_suffix(".progress.jsonl")
    with progress.open("x"):
        pass
    try:
        result = audit(args.output.resolve(), progress)
    except Exception as exc:
        result = dict(audit_method=METHOD, audit_status="AUDIT_ERROR", source_status="INVALID_ABORT", counts_toward_verdict=False,
                      generated_model_calls=0, error=dict(type=type(exc).__name__, message=str(exc)),
                      original_source_summary=read(args.output / "summary.json"), progress_path=str(progress))
    with args.audit_output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["audit_status"], result.get("known_attempted_accounting", result.get("error")), flush=True)
    return 0 if result["audit_status"] == "ACCOUNTING_AND_ABORT_INTEGRITY_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
