"""Additive R4 replay audit. Refuses to run until collection has a final summary.

No models are loaded and no generation occurs. SQLite is read-only/immutable;
policy/context/task/authority replay is performed only after collection ends.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import random
import sqlite3
import subprocess
import sys

from pheroos.kernel import RuntimeScope
from pheroos_runtime.authority import authorize, authorize_r3
from pheroos_bench import r4_tasks as tasks
from audit_r3_session_capability import check, count, digest, equal, event, file_hash, framing, read, wire

METHOD = "r4_session_scaling_pilot_v1"
COUNTS = (1, 2, 4, 8, 16, 32)
POLICIES = ("private", "blackboard", "dedup_ttl", "versioned")
WORLDS = ("code_repair/bounded_increment", "code_repair/cyclic_offset",
          "evidence_revision/route_quota", "evidence_revision/ready_window")
MODELS = {
    "small": ("Qwen/Qwen2.5-Coder-1.5B-Instruct", "2e1fd397ee46e1388853d2af2c993145b0f1098a",
              "600319fcf68b230820502b61767b49ce375316a2d23fe4708126ff5e5fbc26c8"),
    "medium": ("Qwen/Qwen2.5-Coder-3B-Instruct", "488639f1ff808d1d3d0ba301aef8c11461451ec5",
               "cf4593f14704152d28ea15c6630ee7abaca52580973524a386e05ba217391777"),
}
HISTORY_FIELDS = ("id", "world_id", "step", "agent", "task_version", "valid", "feedback", "artifact",
                  "origin_identity", "action", "semantic_action", "runtime_artifact_ref")
COUNTERS = ("actual_tokens", "reserved_tokens", "unknown_tokens", "unknown_calls", "model_calls", "tool_calls",
            "control_operations", "processing_bytes", "request_bytes", "response_bytes", "event_bytes",
            "communication_bytes", "elapsed_ns", "model_elapsed_ns", "model_load_ns", "evaluator_elapsed_ns")


def version(world, step):
    return 1 if world.startswith("code_repair/") or step < 16 else 2


def model_for(condition, step):
    return "medium" if condition["cohort"] == "medium" or condition["cohort"] == "mixed" and step >= 28 else "small"


def cap(condition):
    return 8192 if condition["regime"] == "fixed_tokens" else 65536


def history(record):
    return {key: deepcopy(record[key]) for key in HISTORY_FIELDS}


def select(policy, records, agent, step, current):
    eligible = list(records)
    if policy == "private":
        eligible = [r for r in eligible if r["agent"] == agent]
    if policy in ("dedup_ttl", "versioned"):
        eligible = [r for r in eligible if step - r["step"] < 8]
    if policy == "versioned":
        eligible = [r for r in eligible if r["task_version"] == current]
    selected, seen = [], set()
    for record in reversed(eligible):
        if policy in ("dedup_ttl", "versioned") and record["origin_identity"] in seen:
            continue
        seen.add(record["origin_identity"])
        selected.append(record)
        if len(selected) == 4:
            break
    return deepcopy(selected[::-1])


def declared_conditions():
    conditions = []
    def add(cohort, policy, n, regime):
        conditions.append(dict(id=f"{regime}-{cohort}-{policy}-n{n}", cohort=cohort, policy=policy, agents=n, regime=regime))
    for policy in POLICIES:
        for n in COUNTS:
            add("small", policy, n, "fixed_calls")
    for cohort in ("medium", "mixed"):
        for policy in ("private", "blackboard"):
            for n in (1, 4, 16, 32):
                add(cohort, policy, n, "fixed_calls")
    for regime in ("fixed_tokens", "fixed_deadline"):
        for policy in ("private", "blackboard"):
            for n in COUNTS:
                add("small", policy, n, regime)
        add("medium", "private", 1, regime)
    return conditions


def declared_order(config):
    groups, randomizer = {}, random.Random(3137)
    for condition in config["conditions"]:
        groups.setdefault((condition["regime"], condition["cohort"]), []).extend(
            dict(world_id=w, condition_id=condition["id"]) for w in WORLDS)
    result = []
    for group in groups.values():
        randomizer.shuffle(group)
        result.extend(group)
    return result


def frozen_inputs(output):
    # This sentinel is written only after collection, model cleanup and final checks.
    check((output / "summary.json").is_file(), "collection unfinished: no final summary; audit must remain idle")
    frozen = read(output / "freeze.json")
    config = frozen["config"]
    equal(config["conditions"], declared_conditions(), "declared 66-condition grid differs")
    equal(config["worlds"], list(WORLDS), "four-world declaration differs")
    equal(config["measurement"], dict(confidence=0.95, bootstrap_resamples=2000, seed=3141, budget_cap=10000), "measurement settings differ")
    for key, expected in dict(method_version=METHOD, phase="pilot", counts_toward_verdict=False, steps=32,
            token_cap=65536, binding_token_cap=8192, max_calls=64, max_new_tokens=256, context_tokens=2048,
            context_bytes=32768, artifact_bytes=32768, deadline_seconds=30, seed=3109, order_seed=3137,
            mixed_medium_start_step=28).items():
        equal(config[key], expected, "frozen configuration differs: " + key)
    check(frozen["method_version"] == METHOD and frozen["counts_toward_verdict"] is False, "invalid freeze metadata")
    check(not (output / "source-drift.json").exists(), "collection recorded source drift")
    environment = read(output / "environment.json")
    check(environment["hardware_concurrency"] == 1 and environment["paid_api"] is False
          and environment["monetary_cost"] is None, "physical concurrency/cost declaration differs")
    equal(environment["python"], frozen["python"], "environment interpreter differs")
    checked_files = {}
    for name, expected in frozen["source_sha256"].items():
        check(file_hash(name) == expected, "frozen source differs: " + name)
        checked_files[name] = expected
    import pheroos, pheroos_runtime, audit_r3_session_capability as helpers
    for module in (tasks, pheroos, pheroos_runtime):
        check(str(Path(module.__file__).resolve()) in checked_files, "audit imported an unfrozen source")
    check(sys.version == frozen["python"] and Path(sys.executable).resolve() == Path(frozen["interpreter"]).resolve(), "interpreter changed")
    for name, expected in frozen["packages"].items():
        check(importlib.metadata.version(name) == expected, "package identity changed: " + name)
    from transformers import AutoTokenizer
    tokenizers, model_paths = {}, {}
    for key, (repository, revision, manifest_hash) in MODELS.items():
        equal(config["models"][key], dict(repository=repository, revision=revision, precision="float16",
               quantization=None, manifest_sha256=manifest_hash), "model config differs")
        manifest = frozen["model_manifests"][key]
        for field, value in (("repository", repository), ("revision", revision), ("precision", "float16"), ("quantization", None)):
            equal(manifest[field], value, "model manifest identity differs")
        paths = [Path(p).parent for p in checked_files if p.endswith("/manifest.json") and read(p) == manifest]
        check(len(paths) == 1, "ambiguous model manifest root")
        root = paths[0]
        check(file_hash(root / "manifest.json") == manifest_hash, "raw model manifest differs")
        for name, expected in manifest["sha256"].items():
            path = (root / name).resolve()
            check(path.is_relative_to(root.resolve()) and file_hash(path) == expected, "model member differs: " + name)
            checked_files[str(path)] = expected
        check(sum((root / p).stat().st_size for p in manifest["sha256"]) == manifest["size_bytes"], "model byte total differs")
        tokenizers[key] = AutoTokenizer.from_pretrained(root, local_files_only=True, trust_remote_code=False)
        model_paths[key] = str(root)
    return frozen, checked_files, tokenizers, model_paths, helpers


def read_database(path, snapshot):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        check(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity failure")
        for table in ("run", "work", "calls", "artifacts"):
            rows = [dict(r) for r in db.execute("SELECT * FROM " + table + " ORDER BY rowid")]
            equal(rows[0] if table == "run" else rows, snapshot[table], "SQLite snapshot mismatch: " + table)
        equal([json.loads(r[0]) for r in db.execute("SELECT value FROM events ORDER BY seq")], snapshot["events"], "SQLite event mismatch")
        checkpoints = [dict(r) for r in db.execute("SELECT * FROM checkpoints ORDER BY agent")]
        check(db.execute("SELECT count(*) FROM mailbox").fetchone()[0] == 0, "undeclared mailbox usage")
    return checkpoints


def score(world, step, published, cache):
    candidates = [r for r in published if r["valid"] is True and r["task_version"] == version(world, step)
                  and r["artifact"]["kind"] == "submitted_candidate"]
    if not candidates:
        return False
    latest = candidates[-1]
    key = (world, version(world, step), digest(latest["artifact"]))
    if key not in cache:
        # The public selector is independently reconstructed; the unchanged hidden
        # task evaluator is replayed once per distinct current candidate.
        cache[key] = tasks.score(world, step, [latest])
    return cache[key]


def decoded_call(call):
    return dict(call, request=json.loads(call["request"]), response=json.loads(call["response"]) if call["response"] else None)


def artifact_read(artifact):
    authority = json.loads(artifact["authority"])
    return dict(artifact, value=json.loads(artifact["value"]), authority=authority, scope_ref=authority["scope_ref"])


def audit_episode(output, row, condition, tokenizers, identities, score_cache):
    world, cid = row["world_id"], row["condition_id"]
    directory = output / "episodes" / cid / world
    equal(read(directory / "episode.json"), row, "episode JSONL/file mismatch")
    snapshot = read(directory / "snapshot.json")
    checkpoints = read_database(directory / "session.sqlite", snapshot)
    equal(row["ledger_calls"], snapshot["calls"], "snapshot/call export mismatch")
    equal(row["ledger_events"], snapshot["events"], "snapshot/event export mismatch")
    check(row["method_version"] == METHOD and row["phase"] == "pilot" and row["counts_toward_verdict"] is False, "episode identity/phase differs")
    check(row["status"] == "complete", "source INVALID_ABORT: complete inference must remain blocked")
    check(row["stop_reason"] in ("call_limit", "budget", "deadline"), "unexpected complete stop")
    stopped = row["stop_reason"] != "call_limit"
    run_id = f"r4-{world}-{cid}"
    limits = dict(token_cap=cap(condition), max_calls=64, context_bytes=32768, artifact_bytes=32768,
                  mailbox_bytes=4096, mailbox_messages=16)
    equal(snapshot["run"], dict(id=1, run_id=run_id, status="cancelled" if stopped else "completed",
          generation=int(stopped), enabled=int(not stopped), agents=wire([f"agent{i}" for i in range(condition["agents"])]),
          limits=wire(limits)), "Session run/limit/current-generation mismatch")
    check(len(snapshot["work"]) == 32, "missing declared global work")
    controls = []
    def control(operation, value=None, operations=1):
        controls.append(dict(operation=operation, operations=operations, bytes=len(wire(value).encode()) if value is not None else 0))
    control("session.create")
    trace = [event("created", "", dict(run_id=run_id, limits=limits))]
    artifacts = {a["ref"]: a for a in snapshot["artifacts"]}
    calls = {c["id"]: c for c in snapshot["calls"]}
    check(len(calls) == len(snapshot["calls"]), "duplicate call ID")
    published, used, expected_artifacts, expected_checkpoints = [], [], [], {}
    communication, trims, prompt_checks, actual, inputs, outputs, model_elapsed = 0, 0, 0, 0, 0, 0, 0
    model_tokens, model_calls, per_agent = Counter(), Counter(), Counter()
    invalid_tokens, late_tokens, authority_checks = 0, 0, 0
    abandoned = []
    for step, record in enumerate(row["records"]):
        check(step < 32, "more than 32 aggregate turns")
        agent, current, key = f"agent{step % condition['agents']}", version(world, step), model_for(condition, step)
        work = f"turn{step}"
        equal((record["id"], record["step"], record["agent"], record["task_version"], record["model_ref"]),
              (f"step{step}", step, agent, current, key), "round-robin/model/version allocation differs")
        previous = [history(r) for r in published[-32:]]
        selected = select(condition["policy"], previous, agent, step, current)
        control("policy.select", previous, len(previous) + 1)
        for item in selected:
            stored = artifact_read(artifacts[item["runtime_artifact_ref"]])
            check(all(wire(item[k]) == wire(v) for k, v in stored["value"].items()), "selected task fact differs from durable publication")
            control("artifact.read", stored)
        messages = tasks.messages_for(world, step, selected)
        control("context.encode", messages)
        preflight = []
        while True:
            prompt = len(tokenizers[key].apply_chat_template(messages, add_generation_prompt=True, tokenize=True))
            prompt_checks += 1
            control("model.tokenize", messages)
            preflight.append(dict(prompt_tokens=prompt, messages_sha256=digest(messages), selected_ids=[r["id"] for r in selected]))
            if prompt + 256 <= 2048:
                break
            check(bool(selected), "public instructions exceed frozen context cap")
            selected, trims = selected[1:], trims + 1
            messages = tasks.messages_for(world, step, selected)
            control("context.trim", messages)
        equal(record["preflight"], preflight, "actual offline tokenizer/context trim replay differs")
        equal(record["messages"], messages, "exact public model context differs")
        selected_ids = [r["id"] for r in selected]
        equal(record["selected_ids"], selected_ids, "selected provenance IDs differ")
        communication += sum(len(wire(r).encode()) for r in selected if r["agent"] != agent)
        control("session.claim")
        control("session.checkpoint")
        trace.extend([event("claimed", work, dict(task_id=work, version=current, owner=agent, epoch=1)),
                      event("checkpointed", work, dict(agent=agent, bytes=len(wire(dict(selected_ids=selected_ids)).encode()), generation=0))])
        expected_checkpoints[agent] = dict(agent=agent, work_id=work, version=current, generation=0, value=wire(dict(selected_ids=selected_ids)))
        scope = RuntimeScope("session-v1", run_id, work)
        ids = [cid for cid in (f"generate-{step}", f"evaluate-{step}") if cid in calls]
        equal(record["receipt_ids"], ids, "record/call ID binding differs")
        framed = None
        if record["response"] is not None and "framing" in record:
            framed, diagnostic = framing(record["response"]["text"])
            equal(record["framing"], diagnostic, "raw strict framing differs")
        for index, call_id in enumerate(ids):
            call = calls[call_id]
            is_model = call_id.startswith("generate-")
            action = "model.generate" if is_model else "tool.evaluate"
            request = dict(task_id=work, version=current, model_ref=key, model_identity=identities[key], messages=messages,
                           max_new_tokens=256, seed=3109 + WORLDS.index(world) * 100 + step) if is_model else dict(
                           task_id=work, version=current, tool_ref="task.evaluate",
                           arguments=dict(world=world, step=step, memory=selected, text=framed))
            equal(json.loads(call["request"]), request, "exact dispatched request/model identity differs")
            check(len(call["request"].encode()) <= 32768, "request exceeds common wire cap")
            expected_prompt, maximum = (prompt, 256) if is_model else (0, 0)
            equal((call["id"], call["work_id"], call["version"], call["epoch"], call["action"], call["prompt"], call["maximum"], call["reserved"]),
                  (call_id, work, current, 1, action, expected_prompt, maximum, expected_prompt + maximum), "call reservation/binding differs")
            check(actual + count(call["reserved"]) <= cap(condition), "reservation exceeded common token cap")
            trace.append(event("reserved", work, dict(call_id=call_id, tokens=call["reserved"])))
            used.append(call_id)
            check(call["state"] in ("received", "abandoned"), "unresolved/rejected receipt cannot support complete source")
            if call["state"] == "abandoned":
                check(stopped and call["response"] is None and call["authority"] is None and count(call["actual"]) == 0,
                      "abandoned reservation has invented execution/authority")
                abandoned.append((work, call_id, call["reserved"]))
                continue
            response = json.loads(call["response"])
            equal(response, record["response" if is_model else "evaluation"], "raw response differs from SQLite receipt")
            check(len(call["response"].encode()) <= 32768, "received response exceeds common bound")
            check(count(response["prompt_tokens"]) == expected_prompt and count(response["completion_tokens"]) <= maximum,
                  "receipt token components differ")
            charge = response["prompt_tokens"] + response["completion_tokens"]
            check(count(call["actual"]) == charge, "actual charge differs from receipt")
            count(response["adapter_elapsed_ns"])
            authority = (authorize_r3 if is_model else authorize)(scope, work, current, action, request)
            equal(json.loads(call["authority"]), authority, "current public-core dispatch authority differs")
            authority_checks += 1
            trace.extend([event("dispatched", work, dict(call_id=call_id, authority=authority)),
                          event("received", work, dict(call_id=call_id, actual_tokens=charge, response_digest=digest(response)))])
            actual, inputs, outputs = actual + charge, inputs + response["prompt_tokens"], outputs + response["completion_tokens"]
            if is_model:
                check(response["model_ref"] == key and type(response["text"]) is str, "raw proposal/model binding differs")
                model_elapsed += count(response["elapsed_ns"])
                count(response["peak_cuda_bytes"])
                model_tokens[key] += charge
                model_calls[key] += 1
                per_agent[agent] += 1
                control("model.driver", response)
                control("receipt.binding", decoded_call(call))
                if "framing" in record:
                    control("framing", dict(raw=response["text"], text=framed, diagnostic=record["framing"]),
                            1 + record["framing"]["parse_operations"])
            else:
                check(record["response"] is not None and framed is not None and response["tool_ref"] == "task.evaluate", "tool lacks admitted model request")
                result = tasks.apply(world, step, selected, framed)
                equal(response["artifact"], result, "original public task/tool evaluator replay differs")
                control("tool.driver", response)
                control("receipt.binding", decoded_call(call))
                control("tool.verify", result)
        if record["response"] is not None and record["evaluation"] is None:
            late_tokens += calls[f"generate-{step}"]["actual"]
        if record["evaluation"] is not None and not record["evaluation"]["artifact"]["valid"]:
            invalid_tokens += calls[f"generate-{step}"]["actual"]
        if record["published"]:
            check(record["evaluation"] is not None, "publication lacks a settled tool receipt")
            fact = record["evaluation"]["artifact"]
            for field, value in fact.items():
                equal(record[field], value, "published record differs from checked fact")
            payload = dict(task_id=work, version=current, artifact=fact, call_id=f"evaluate-{step}",
                           response_digest=digest(record["evaluation"]), scope_ref=scope.scope_ref)
            authority = authorize_r3(scope, work, current, "artifact.publish", payload)
            authority_checks += 1
            ref = "sha256:" + digest(payload)
            equal(record["runtime_artifact_ref"], ref, "runtime artifact reference differs")
            artifact = dict(ref=ref, work_id=work, version=current, publisher=agent, value=wire(fact), call_id=f"evaluate-{step}",
                            response_digest=payload["response_digest"], authority=wire(authority))
            expected_artifacts.append(artifact)
            trace.append(event("published", work, dict(artifact_ref=ref, call_id=f"evaluate-{step}", version=current,
                         response_digest=payload["response_digest"], authority=authority)))
            control("session.publish")
            count(record["elapsed_ns"])
            published.append(record)
        else:
            check(record["valid"] is False and record["artifact"] is None and record["prefix_success"] is False,
                  "unpublished model/tool response became task evidence")
        check(record["response"] is None or f"generate-{step}" in ids, "proposal has no durable receipt")
        check(record["evaluation"] is None or f"evaluate-{step}" in ids, "tool result has no durable receipt")
    check(len(used) == len(calls) <= 64, "hidden/orphan/excess call")
    equal(used, list(calls), "durable call order differs")
    equal(expected_artifacts, snapshot["artifacts"], "publication database contains different/extra artifacts")
    equal(checkpoints, sorted(expected_checkpoints.values(), key=lambda r: r["agent"]), "private checkpoint database differs")
    for step, work_row in enumerate(snapshot["work"]):
        declaration = dict(id=f"turn{step}", version=version(world, step), dependencies=[f"turn{step-1}"] if step else [],
                           agents=[f"agent{step % condition['agents']}"], actions=["model.generate", "tool.evaluate"])
        done = any(r["step"] == step and r["published"] for r in row["records"])
        equal(work_row, dict(id=f"turn{step}", version=version(world, step), declaration=wire(declaration),
             status="done" if done else "cancelled", owner=None, epoch=int(step < len(row["records"])), expires=None,
             generation=0), "final work state differs from current cancellation/publication boundary")
    if stopped:
        for work, call_id, tokens in abandoned:
            trace.append(event("reservation_abandoned", work, dict(call_id=call_id, released_tokens=tokens)))
        trace.append(event("cancelled", "", dict(generation=1)))
        control("session.cancel")
    equal(snapshot["events"], trace, "exact causal Session trace differs")
    control("session.snapshot")
    success_steps = []
    for index, record in enumerate(published):
        success = score(world, record["step"], published[:index + 1], score_cache)
        equal(record["prefix_success"], success, "post-execution prefix score differs")
        if success:
            success_steps.append(record["step"])
        control("evaluator.score")
    final_step = len(row["records"]) - 1 if row["records"] else 0
    equal(row["success"], score(world, 31, published, score_cache), "same final-version objective differs")
    equal(row["current_snapshot_success"], score(world, final_step, published, score_cache), "current-snapshot diagnostic differs")
    control("evaluator.score", operations=2)
    equal(row["controls"], controls, "declared logical control operations/bytes differ")
    equal(row["success_steps"], success_steps, "prefix success steps differ")
    check(count(row["final_step"]) == final_step and count(row["context_trim_count"]) == trims, "final step/context trim accounting differs")
    check(count(row["active_agents"]) == len(per_agent), "accepted-response agent allocation differs")
    equal(row["final_version_reached"], any(r["response"] is not None and r["task_version"] == version(world, 31) for r in row["records"]), "final-version reached diagnostic differs")
    accounting = row["accounting"]
    for field in COUNTERS:
        count(accounting[field])
    check(accounting["model_elapsed_ns"] <= accounting["elapsed_ns"]
          and accounting["model_load_ns"] <= accounting["elapsed_ns"], "component elapsed time exceeds execution time")
    check(accounting["monetary_cost"] is None, "local monetary cost was fabricated")
    totals = dict(actual_tokens=actual, reserved_tokens=0, unknown_tokens=0, unknown_calls=0,
                  model_calls=sum(model_calls.values()), tool_calls=sum(c["state"] == "received" and c["action"] == "tool.evaluate" for c in calls.values()),
                  request_bytes=sum(len(c["request"].encode()) for c in calls.values()),
                  response_bytes=sum(len((c["response"] or "").encode()) for c in calls.values()), event_bytes=sum(len(wire(e).encode()) for e in trace),
                  communication_bytes=communication, model_elapsed_ns=model_elapsed,
                  control_operations=sum(c["operations"] for c in controls), processing_bytes=sum(c["bytes"] for c in controls))
    for field, expected in totals.items():
        check(accounting[field] == expected, "episode accounting differs: " + field)
    for field in ("actual_tokens", "reserved_tokens", "unknown_tokens", "unknown_calls"):
        check(count(snapshot[field]) == totals[field], "snapshot totals differ from database receipts")
    check(count(snapshot["call_count"]) == len(calls), "snapshot call count differs")
    reason = row["stop_reason"]
    if reason == "call_limit":
        check(len(row["records"]) == len(published) == totals["model_calls"] == totals["tool_calls"] == 32, "full call allocation not exercised")
        check(len(per_agent) == condition["agents"], "declared full-run agents were idle")
        check(row["errors"] == [], "full run has unclassified errors")
    elif reason == "deadline":
        check(condition["regime"] == "fixed_deadline" and accounting["elapsed_ns"] >= 30_000_000_000, "unjustified deadline stop")
        check(all(e["type"] == "DeadlineReached" and e["stage"] == "valid_stop" for e in row["errors"]), "unexpected deadline error")
    else:
        check(row["records"] and not row["records"][-1]["published"], "budget stop has no partial next attempt")
        last = row["records"][-1]
        needed = last["preflight"][-1]["prompt_tokens"] + 256 if f"generate-{last['step']}" not in calls else 0
        check(len(calls) >= 64 or actual + needed > cap(condition), "budget stop was not binding")
        check(row["errors"] and all(e["type"] == "BudgetExceeded" and e["stage"] == "valid_stop" for e in row["errors"]), "unexpected budget error")
    return dict(world_id=world, condition_id=cid, success=row["success"], stop_reason=reason,
                actual_tokens=actual, input_tokens=inputs, output_tokens=outputs, model_calls=dict(model_calls),
                model_tokens=dict(model_tokens), tool_calls=totals["tool_calls"], public_invalid_model_tokens=invalid_tokens,
                model_tokens_without_tool_evaluation=late_tokens, active_agents=len(per_agent), per_agent_model_calls=dict(per_agent),
                authority_checks=authority_checks, tokenizer_checks=prompt_checks, events=len(trace), publications=len(published),
                checkpoint_agents=len(checkpoints), context_trims=trims, current_snapshot_success=row["current_snapshot_success"],
                final_version_reached=row["final_version_reached"])


def audit(output):
    check((output / "summary.json").is_file(), "collection unfinished: do not run this audit during deadline collection")
    paths = [output / p for p in ("freeze.json", "environment.json", "order.json", "model-loads.json", "episodes.jsonl", "summary.json")]
    paths += sorted((output / "episodes").rglob("episode.json")) + sorted((output / "episodes").rglob("snapshot.json")) + sorted((output / "episodes").rglob("session.sqlite"))
    before = {str(p.resolve()): file_hash(p) for p in paths}
    frozen, source_files, tokenizers, model_paths, helpers = frozen_inputs(output)
    config, summary = frozen["config"], read(output / "summary.json")
    check(summary["status"] == "PILOT_COMPLETE" and summary["source_status"] == "VALID_COMPLETE", "source collection is explicitly invalid; usable inference blocked")
    order = declared_order(config)
    equal(read(output / "order.json"), order, "predeclared randomized execution order differs")
    with (output / "episodes.jsonl").open() as stream:
        rows = [json.loads(line, object_pairs_hook=helpers.base._object, parse_constant=helpers.base._nonfinite) for line in stream]
    equal([dict(world_id=r["world_id"], condition_id=r["condition_id"]) for r in rows], order, "missing/duplicate/reordered 264-cell grid")
    loads = read(output / "model-loads.json")
    identities = {}
    for load in loads:
        check(load["status"] == "loaded" and load["model_class"] == "Qwen2ForCausalLM", "model load failed or class changed")
        count(load["elapsed_ns"])
        key, identity = load["model_ref"], load["identity"]
        check(key in MODELS, "undeclared loaded checkpoint")
        equal(identity["model_manifest"], frozen["model_manifests"][key], "loaded model manifest differs")
        for field, expected in (("dtype", "float16"), ("python", frozen["python"]), ("torch", frozen["packages"]["torch"]), ("transformers", frozen["packages"]["transformers"])):
            equal(identity[field], expected, "loaded environment differs")
        if key in identities:
            equal(identities[key], identity, "model identity changed between loads")
        identities[key] = identity
    check(set(identities) == set(MODELS), "missing declared model")
    for field in ("cuda", "gpu", "dtype", "torch", "transformers", "python"):
        equal(identities["small"][field], identities["medium"][field], "common model environment differs")
    conditions = {c["id"]: c for c in config["conditions"]}
    expected_loads, resident, outside_load_ns = [], None, 0
    checked, score_cache = [], {}
    for row in rows:
        condition = conditions[row["condition_id"]]
        requests = ([(model_for(condition, 0), False)] if condition["cohort"] != "mixed" else [])
        requests += [(model_for(condition, r["step"]), True) for r in row["records"]]
        within_load_ns = 0
        for key, within_episode in requests:
            if key != resident:
                load = loads[len(expected_loads)]
                check(load["model_ref"] == key, "resident model replacement order differs")
                if within_episode:
                    within_load_ns += load["elapsed_ns"]
                else:
                    outside_load_ns += load["elapsed_ns"]
                expected_loads.append(key)
                resident = key
        checked.append(audit_episode(output, row, condition, tokenizers, identities, score_cache))
        check(row["accounting"]["model_load_ns"] >= within_load_ns, "mixed checkpoint load time was omitted from episode time")
        checked[-1]["within_episode_model_load_events_ns"] = within_load_ns
        print("verified", len(checked), "/", len(rows), row["condition_id"], row["world_id"], flush=True)
    equal([load["model_ref"] for load in loads], expected_loads, "resident model replacement/setup schedule differs")
    expected_totals = []
    for key, condition in sorted(conditions.items()):
        selected = [row for row in rows if row["condition_id"] == key]
        expected_totals.append(dict(condition_id=key, condition=condition, n_worlds=4,
            successes=sum(row["success"] for row in selected), quality_mean=sum(row["success"] for row in selected) / 4,
            logical_operations=sum(sum(row["accounting"][k] for k in ("model_calls", "tool_calls", "control_operations")) for row in selected),
            accounting={k: sum(row["accounting"][k] for row in selected) for k in COUNTERS}, monetary_cost=None))
    equal(summary["by_condition"], expected_totals, "paired-source summary condition totals differ")
    source_accounting = [dict(row_index=index, world_id=row["world_id"], condition_id=row["condition_id"], status="complete",
        reported_accounting={k: row["accounting"][k] for k in COUNTERS}, monetary_cost=None,
        ledger_actual_tokens=row["accounting"]["actual_tokens"], ledger_unknown_calls=0, ledger_unknown_tokens=0,
        ledger_partial_or_malformed=False) for index, row in enumerate(rows)]
    equal(summary["source_accounting"], source_accounting, "retained source accounting differs from audited receipts")
    for field, expected in dict(method_version=METHOD, phase="pilot", counts_toward_verdict=False, expected_episodes=264,
                                n_episodes=264, n_worlds=4, event_bytes_verified=True).items():
        equal(summary[field], expected, "summary metadata differs")
    equal({str(p.resolve()): file_hash(p) for p in paths}, before, "audit changed original collection evidence")
    totals = {k: sum(r["accounting"][k] for r in rows) for k in COUNTERS}
    totals.update(episodes=len(rows), invalid_aborts=0, input_tokens=sum(r["input_tokens"] for r in checked),
                  output_tokens=sum(r["output_tokens"] for r in checked), authority_checks=sum(r["authority_checks"] for r in checked),
                  tokenizer_checks=sum(r["tokenizer_checks"] for r in checked), publications=sum(r["publications"] for r in checked),
                  unique_hidden_score_replays=len(score_cache))
    return dict(audit_method="r4_session_scaling_independent_audit_v1", status="AUDIT_PASS", counts_toward_verdict=False,
        created_utc=datetime.now(timezone.utc).isoformat(), generated_model_calls=0, source_method_version=METHOD,
        source_config=config, environment=read(output / "environment.json"),
        original_evidence_unchanged=True, evidence_sha256=before, frozen_files_checked=len(source_files),
        checked_input_sha256=source_files, model_paths=model_paths, model_identities=identities, model_loads=len(loads),
        model_load_elapsed_ns=sum(load["elapsed_ns"] for load in loads), outside_episode_model_load_elapsed_ns=outside_load_ns,
        totals=totals, episode_checks=checked,
        by_condition=expected_totals, audit_source_sha256={str(Path(p).resolve()): file_hash(p) for p in (__file__, helpers.__file__)},
        bench_base_commit=frozen["bench_base_commit"], external_runtime_audit_head=subprocess.check_output(
            ["git", "-C", "/home/scott/projects/PheroOS-runtime", "rev-parse", "HEAD"], text=True).strip(),
        limitations=["Pilot only; four constructed worlds are the independent units, not counts/turns/policies.",
          "No generation or GPU calls in audit; tokenizer checks are offline CPU work after collection.",
          "Completion token IDs are absent; actual completion charges reconcile to durable receipts and frozen tensor-length implementation.",
          "Authority projections, current generations and causal lifecycle ordering replay exactly; historical monotonic deadline gate instants are not independently timestamped in the trace.",
          "Deadline outcomes describe this sequential run and its concurrent CPU environment, not isolated hardware latency/throughput or physical GPU scaling.",
          "Private N>=8 evidence allocation is structurally insufficient; outperforming it alone is not proof of useful coordination.",
          "Successful audit does not promote a policy or complete R5/master-goal requirements."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    # Reject an in-progress collection before importing tokenizers or hashing weights.
    check((args.output / "summary.json").is_file(), "collection unfinished; heavy audit remains disabled")
    check(not args.audit_output.exists(), "exclusive new additive audit output required")
    try:
        result = audit(args.output.resolve())
    except Exception as exc:
        result = dict(audit_method="r4_session_scaling_independent_audit_v1", status="INVALID_ABORT", counts_toward_verdict=False,
                      generated_model_calls=0, error=dict(type=type(exc).__name__, message=str(exc)),
                      source_summary=read(args.output / "summary.json"),
                      source_accounting_label="Original reported costs retained; an audit failure does not make them zero or validated.")
    with args.audit_output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["status"], result.get("totals", result.get("error")), flush=True)
    return 0 if result["status"] == "AUDIT_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
