"""Finite capability diagnostic using the separately installed Session ledger."""

from __future__ import annotations

import argparse
from copy import deepcopy
import gc
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import sys
import time

from . import r3_framed_pilot as framing, r3_tool_tasks as tasks

METHOD = "r3_session_capability_v1"
CONDITIONS = ("autonomous_single", "supplied_current_inspections")
MODELS = {
    "qwen_1_5b": {"repository": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
                  "revision": "2e1fd397ee46e1388853d2af2c993145b0f1098a",
                  "manifest_sha256": "600319fcf68b230820502b61767b49ce375316a2d23fe4708126ff5e5fbc26c8"},
    "qwen_3b": {"repository": "Qwen/Qwen2.5-Coder-3B-Instruct",
                "revision": "488639f1ff808d1d3d0ba301aef8c11461451ec5",
                "manifest_sha256": "cf4593f14704152d28ea15c6630ee7abaca52580973524a386e05ba217391777"},
}


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(wire(value).encode()).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return sha256_file(stream)


def sha256_file(stream):
    result = sha256()
    for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
        result.update(block)
    return result.hexdigest()


def save(path, value):
    with Path(path).open("x") as stream:
        stream.write(wire(value) + "\n")


def configuration():
    return dict(method_version=METHOD, phase="capability_diagnostic", models=deepcopy(MODELS), conditions=list(CONDITIONS),
                worlds=tasks.world_ids(), steps=6, diagnostic_step=5, max_new_tokens=256,
                context_tokens=2048, context_bytes=65536, artifact_bytes=65536,
                episode_token_cap=12288, max_calls=16, seed=2081,
                model_class="Qwen2ForCausalLM", precision="float16", quantization=None,
                counts_toward_verdict=False)


def runtime():
    # Bench never installs/imports model dependencies or a runtime implicitly.
    from pheroos_runtime.session_v1 import Session
    from pheroos_runtime.session_driver_v1 import SessionDriver, LocalModelAdapter
    return Session, SessionDriver, LocalModelAdapter


def inspection_targets(world):
    public = json.loads(tasks.messages_for(world, 5, [])[1]["content"])["task"]
    return public["test_index"] if "test_index" in public else [x["source_id"] for x in public["source_index"]]


def evaluation(arguments):
    return {"kind": "r3_evaluation_fact_v1", "input_digest": digest(arguments),
            "world_id": arguments["world"], "step": arguments["step"],
            "result": tasks.apply(arguments["world"], arguments["step"], arguments["memory"], arguments["text"])}


def bound_receipt(session, call_id, lease, action, request, response):
    stored = session.call(call_id)
    if ((stored["work_id"], stored["version"], stored["epoch"], stored["action"], stored["state"])
            != (lease.task_id, lease.version, lease.epoch, action, "received")
            or wire(stored["request"]) != wire(request) or wire(stored["response"]) != wire(response)):
        raise ValueError("raw reply or request differs from the bound settled Session receipt")
    return stored


def record(reference, world, step, fact):
    result = fact["result"]
    return {"id": reference, "agent": "agent0", "step": step, "task_version": tasks.version(world, step),
            **{key: result[key] for key in ("valid", "feedback", "artifact", "action", "semantic_action")},
            "receipt_digest": digest(result["artifact"])}


def fitted_messages(model, world, step, memory, trim):
    memory, preflight, dropped = deepcopy(memory), [], []
    while True:
        messages = tasks.messages_for(world, step, memory)
        started = time.monotonic_ns()
        count = model.count_tokens(messages)
        preflight.append({"prompt_tokens": count, "messages_sha256": digest(messages),
                          "elapsed_ns": time.monotonic_ns() - started, "request_bytes": len(wire(messages).encode())})
        if type(count) is not int or count < 1:
            raise ValueError("invalid actual tokenizer count")
        if count + 256 <= 2048:
            return messages, memory, preflight, dropped
        if not trim or not memory:
            raise ValueError("declared task/current inspections exceed context bound")
        dropped.append(memory.pop(0)["id"])


def episode(model, config, model_id, world, condition, output):
    if wire(config) != wire(configuration()) or model_id not in MODELS or condition not in CONDITIONS:
        raise ValueError("unsupported capability configuration or grid member")
    Session, SessionDriver, _ = runtime()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    identity = f"{model_id}-{tasks.world_ids().index(world)}-{condition}"
    targets = inspection_targets(world) if condition == CONDITIONS[1] else []
    schedule = [(f"inspect-{index}", 5, target) for index, target in enumerate(targets)]
    schedule += [(f"turn-{step}", step, None) for step in (range(6) if not targets else [5])]
    work = [{"id": name, "version": tasks.version(world, step), "agents": ["agent0"],
             "dependencies": [schedule[index - 1][0]] if index else [],
             "actions": ["model.generate", "tool.evaluate"]}
            for index, (name, step, target) in enumerate(schedule)]
    session, records, turns, error, ledger = None, [], [], None, None
    started = time.monotonic_ns()
    try:
        session = Session.create(output / "session.sqlite", identity, agents=["agent0"], work=work,
            token_cap=config["episode_token_cap"], max_calls=config["max_calls"],
            context_bytes=config["context_bytes"], artifact_bytes=config["artifact_bytes"])
        driver = SessionDriver(session, models={model_id: model}, tools={"evaluate_action": evaluation},
                               context_tokens=config["context_tokens"])
        for name, step, target in schedule:
            lease = session.claim("agent0", name, lease_seconds=120)
            row = {"work_id": name, "step": step, "inspection_target": target, "response": None,
                   "evaluation_response": None, "publication": None, "context_preflight": [], "dropped_ids": []}
            turns.append(row)
            if target is None:
                memory = tasks.memory_for("single", records, step, tasks.version(world, step)) if not targets else deepcopy(records)
                messages, memory, row["context_preflight"], row["dropped_ids"] = fitted_messages(model, world, step, memory, not targets)
                call_id = name + ":model"
                response = driver.generate(lease, call_id, model_id, messages, max_new_tokens=256,
                    seed=config["seed"] + tasks.world_ids().index(world) * 100 + step)
                row["response"] = response
                expected = dict(task_id=name, version=lease.version, model_ref=model_id, model_identity=model.identity,
                                messages=messages, max_new_tokens=256, seed=config["seed"] + tasks.world_ids().index(world) * 100 + step)
                row["model_call"] = bound_receipt(session, call_id, lease, "model.generate", expected, response)
                if response["prompt_tokens"] != row["context_preflight"][-1]["prompt_tokens"]:
                    raise ValueError("generation usage differs from actual context preflight")
                text, row["framing"] = framing.frame(response.get("text"))
            else:
                memory = deepcopy(records)
                text = wire({"action": "inspect", "target": target})
                row["framing"] = {"kind": "declared_inspection", "admitted": True}
            arguments = dict(world=world, step=step, memory=memory, text=text)
            row["consumed_ids"] = [item["id"] for item in memory]
            tool_id = name + ":tool"
            tool_response = driver.evaluate(lease, tool_id, "evaluate_action", arguments)
            row["evaluation_response"] = tool_response
            expected = dict(task_id=name, version=lease.version, tool_ref="evaluate_action", arguments=arguments)
            row["tool_call"] = bound_receipt(session, tool_id, lease, "tool.evaluate", expected, tool_response)
            verification_started = time.monotonic_ns()
            verified = evaluation(deepcopy(arguments))
            row["verification_elapsed_ns"] = time.monotonic_ns() - verification_started
            row["verification_recomputations"] = 1
            reference = session.publish(lease, tool_id, tool_response["artifact"],
                verify=lambda task, value: task == name and wire(value) == wire(verified), authorize=driver.authorization)
            row["publication"] = session.artifact(reference)
            # Only the checked result becomes task history; invalid task artifacts remain None.
            published = row["publication"]["value"]
            records.append(record(reference, world, step, published))
        success = tasks.score(world, 5, records)
    except Exception as exc:
        error, success = {"type": type(exc).__name__, "message": str(exc)}, None
        if session is not None:
            try:
                session.cancel()
            except Exception as cleanup:
                error["cleanup_error"] = f"{type(cleanup).__name__}: {cleanup}"
    if session is not None:
        try:
            ledger = session.snapshot()
        except Exception as exc:
            if error:
                error["snapshot_error"] = f"{type(exc).__name__}: {exc}"
            else:
                error = {"type": type(exc).__name__, "message": str(exc)}
    metrics = dict.fromkeys(("actual_tokens", "usage", "model_calls", "tool_calls", "request_bytes",
                             "response_bytes", "retained_response_bytes", "trace_bytes"))
    accounting_status = "UNRESOLVED"
    if ledger is not None:
        try:
            calls = ledger["calls"]
            actual = sum(_count(c["actual"]) for c in calls if c["actual"] is not None)
            if actual != _count(ledger["actual_tokens"]):
                raise ValueError("Session totals differ from call usage")
            received = [c for c in calls if c["state"] in ("received", "response_rejected")]
            usage = {key: sum(_count(_object(c["response"])[field]) for c in received)
                     for key, field in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"))}
            dispatched = {e["lineage"]["call_id"] for e in ledger["events"] if e["event_type"] == "ext.session.dispatched"}
            metrics = dict(actual_tokens=actual, usage=usage,
                model_calls=sum(c["action"] == "model.generate" and c["id"] in dispatched for c in calls),
                tool_calls=sum(c["action"] == "tool.evaluate" and c["id"] in dispatched for c in calls),
                request_bytes=sum(len(c["request"].encode()) for c in calls),
                response_bytes=sum(_object(c["response"])["response_bytes"] if c["state"] == "response_rejected"
                                   else len((c["response"] or "").encode()) for c in calls),
                retained_response_bytes=sum(len((c["response"] or "").encode()) for c in calls),
                trace_bytes=sum(len(wire(e).encode()) for e in ledger["events"]))
            accounting_status = "UNRESOLVED" if _count(ledger["unknown_calls"]) or _count(ledger["reserved_tokens"]) else "KNOWN"
        except Exception as exc:
            error = error or {"type": type(exc).__name__, "message": str(exc)}
            error["reporting_error"] = f"{type(exc).__name__}: {exc}"
            metrics = dict.fromkeys(metrics)
    if accounting_status == "UNRESOLVED":
        error = error or {"type": "UnresolvedLedger", "message": "missing or unresolved Session accounting"}
    result = dict(method_version=METHOD, phase="capability_diagnostic", counts_toward_verdict=False,
        model_id=model_id, world_id=world, condition=condition,
        outcome="INVALID_ABORT" if error else "success" if success else "failed", error=error,
        accounting_status=accounting_status, **metrics,
        ledger=ledger, records=records, turns=turns, elapsed_ns=time.monotonic_ns() - started)
    save(output / "episode.json", result)
    return result


def verified_inputs(config_path, model_paths, runtime_site):
    if wire(json.loads(Path(config_path).read_text())) != wire(configuration()):
        raise ValueError("unsupported capability configuration")
    Session, _, _ = runtime()
    import pheroos_runtime, pheroos
    installed = Path(pheroos_runtime.__file__).resolve().parent
    if installed.parent != Path(runtime_site).resolve():
        raise ValueError("Session must be imported from the explicit installed target")
    manifests, files = {}, []
    for name, spec in MODELS.items():
        root = Path(model_paths[name]).resolve()
        path = root / "manifest.json"
        manifest = json.loads(path.read_text())
        if (file_hash(path) != spec["manifest_sha256"] or any(manifest.get(k) != spec[k] for k in ("repository", "revision"))
                or manifest.get("precision") != "float16" or manifest.get("quantization") is not None):
            raise ValueError("model does not match the declared immutable identity")
        files.append(path)
        for relative, expected in manifest["sha256"].items():
            member = (root / relative).resolve()
            if not member.is_relative_to(root) or not member.is_file() or file_hash(member) != expected:
                raise ValueError("model member hash mismatch")
            files.append(member)
        manifests[name] = manifest
    bench = Path(__file__).resolve().parents[2]
    files += [Path(__file__), Path(tasks.__file__), Path(framing.__file__), Path(config_path),
              bench / "R3-session-capability-v1-contract.md", bench / "tests/test_r3_session_capability.py",
              *[Path(getattr(framing, name).__file__) for name in ("r3_tasks", "r3_tool_pilot", "r3_pilot")],
              *installed.glob("*.py"), *Path(pheroos.__file__).parent.rglob("*.py"),
              *Path(pheroos.__file__).parent.rglob("*.json"), Path(sys.executable).resolve()]
    frozen = {str(p.resolve()): file_hash(p) for p in files}
    environment = {"python": sys.version, "interpreter": sys.executable, "runtime_root": str(installed),
                   "packages": {name: importlib.metadata.version(name) for name in ("pheroos-runtime", "pheroos", "torch", "transformers")}}
    return dict(config=configuration(), files_sha256=frozen, models=manifests, environment=environment,
                frozen_before_model_loading=True, counts_toward_verdict=False)


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError("accounting requires exact nonnegative integers")
    return value


def _object(text):
    value = json.loads(text, object_pairs_hook=framing.r3_tasks._object, parse_constant=framing.r3_tasks._nonfinite)
    if type(value) is not dict:
        raise ValueError("ledger payload must be a JSON object")
    return value


def reconcile(row):
    ledger = row["ledger"]
    limits = _object(ledger["run"]["limits"])
    config = configuration()
    if any(type(limits.get(key)) is not int or limits[key] != config[target]
           for key, target in (("token_cap", "episode_token_cap"), ("max_calls", "max_calls"),
                               ("context_bytes", "context_bytes"), ("artifact_bytes", "artifact_bytes"))):
        raise ValueError("Session limits differ from declared common budget")
    calls, work = ledger["calls"], {w["id"]: w for w in ledger["work"]}
    if len(work) != len(ledger["work"]) or any(type(w["version"]) is not int or w["version"] < 1 for w in work.values()):
        raise ValueError("invalid or duplicate Session work")
    if type(calls) is not list or len(calls) > config["max_calls"]:
        raise ValueError("invalid Session call list")
    seen, actual, reserved, unknown, unknown_calls = set(), 0, 0, 0, 0
    input_tokens, output_tokens, model_calls, tool_calls = 0, 0, 0, 0
    for call in calls:
        identity, state = call["id"], call["state"]
        if type(identity) is not str or not identity or identity in seen:
            raise ValueError("invalid or duplicate Session call ID")
        seen.add(identity)
        if state not in ("reserved", "dispatched", "received", "response_rejected", "abandoned"):
            raise ValueError("invalid Session call state")
        prompt, maximum, allocation = (_count(call[key]) for key in ("prompt", "maximum", "reserved"))
        if allocation != prompt + maximum:
            raise ValueError("reservation does not match requested token bound")
        request = _object(call["request"])
        task = work.get(call["work_id"])
        if (type(call["work_id"]) is not str or task is None or type(call["version"]) is not int or call["version"] < 1
                or call["version"] != task["version"] or type(call["epoch"]) is not int or call["epoch"] < 1
                or request.get("task_id") != call["work_id"] or type(request.get("version")) is not int
                or request["version"] != call["version"]):
            raise ValueError("receipt request/work/version binding mismatch")
        if call["action"] == "model.generate":
            if (type(request.get("max_new_tokens")) is not int or request["max_new_tokens"] != maximum or maximum != 256
                    or prompt < 1 or allocation > config["context_tokens"]
                    or request.get("model_ref") != row["model_id"] or not call["work_id"].startswith("turn-")):
                raise ValueError("model call differs from declared capability request")
            step = int(call["work_id"].removeprefix("turn-"))
            if (step not in range(6) or request.get("seed") != 2081 + tasks.world_ids().index(row["world_id"]) * 100 + step
                    or type(request.get("seed")) is not int or type(request.get("messages")) is not list
                    or tasks.version(row["world_id"], step) != call["version"]):
                raise ValueError("model call step/seed/context binding mismatch")
            model_calls += state in ("dispatched", "received", "response_rejected")
        elif call["action"] == "tool.evaluate":
            arguments = request.get("arguments")
            if (prompt or maximum or request.get("tool_ref") != "evaluate_action" or type(arguments) is not dict
                    or arguments.get("world") != row["world_id"] or type(arguments.get("step")) is not int
                    or arguments["step"] not in range(6) or tasks.version(row["world_id"], arguments["step"]) != call["version"]):
                raise ValueError("tool receipt request/world/version binding mismatch")
            tool_calls += state in ("dispatched", "received", "response_rejected")
        else:
            raise ValueError("undeclared ledger action")
        if state in ("reserved", "dispatched"):
            if call["actual"] is not None or call["response"] is not None:
                raise ValueError("unfinished call cannot fabricate actual usage or receipt")
            reserved += allocation if state == "reserved" else 0
            unknown += allocation if state == "dispatched" else 0
            unknown_calls += state == "dispatched"
        else:
            measured = _count(call["actual"])
            actual += measured
            if state == "abandoned":
                if measured != 0 or call["response"] is not None:
                    raise ValueError("abandoned reservation has no execution cost/receipt")
                continue
            response = _object(call["response"])
            incoming, outgoing = _count(response.get("prompt_tokens")), _count(response.get("completion_tokens"))
            if incoming != prompt or outgoing > maximum or measured != incoming + outgoing:
                raise ValueError("receipt usage does not reconcile with reserved/actual cost")
            if state == "response_rejected":
                if (response.get("response_rejected") != "response_bytes_exceeded"
                        or type(response.get("response_digest")) is not str or len(response["response_digest"]) != 64
                        or _count(response.get("response_bytes")) <= config["artifact_bytes"]):
                    raise ValueError("invalid retained rejected-response receipt")
            elif call["action"] == "model.generate":
                if response.get("model_ref") != request["model_ref"]:
                    raise ValueError("model response/request binding mismatch")
            else:
                fact = response.get("artifact")
                if (response.get("tool_ref") != request["tool_ref"] or type(fact) is not dict
                        or fact.get("kind") != "r3_evaluation_fact_v1" or fact.get("input_digest") != digest(arguments)
                        or fact.get("world_id") != arguments["world"] or type(fact.get("step")) is not int
                        or fact["step"] != arguments["step"]):
                    raise ValueError("evaluation response/request binding mismatch")
            input_tokens, output_tokens = input_tokens + incoming, output_tokens + outgoing
    if actual + reserved + unknown > config["episode_token_cap"]:
        raise ValueError("common episode cap exceeded")
    expected = dict(actual_tokens=actual, reserved_tokens=reserved, unknown_tokens=unknown,
                    unknown_calls=unknown_calls, call_count=len(calls))
    if any(_count(ledger.get(key)) != value for key, value in expected.items()):
        raise ValueError("Session totals do not reconcile with calls")
    expected_status = "UNRESOLVED" if unknown_calls or reserved else "KNOWN"
    if row["accounting_status"] != expected_status:
        raise ValueError("episode accounting status differs from Session")
    usage = row["usage"]
    if (type(usage) is not dict or set(usage) != {"input_tokens", "output_tokens"}
            or (_count(usage["input_tokens"]), _count(usage["output_tokens"])) != (input_tokens, output_tokens)
            or _count(row["actual_tokens"]) != actual
            or (_count(row["model_calls"]), _count(row["tool_calls"])) != (model_calls, tool_calls)):
        raise ValueError("episode costs/counts do not reconcile with Session receipts")
    return expected


def summarize(rows):
    expected = {(m, w, c) for m in MODELS for w in tasks.world_ids() for c in CONDITIONS}
    if len(rows) != len(expected) or {(r["model_id"], r["world_id"], r["condition"]) for r in rows} != expected:
        raise ValueError("missing or duplicate declared capability episodes")
    for row in rows:
        if (row.get("method_version") != METHOD or row.get("counts_toward_verdict") is not False
                or row.get("outcome") not in ("success", "failed", "INVALID_ABORT")):
            raise ValueError("invalid capability episode metadata")
        if row.get("accounting_status") == "NOT_STARTED":
            if row["outcome"] != "INVALID_ABORT" or row["actual_tokens"] is not None:
                raise ValueError("unattempted episode must not fabricate known accounting")
            continue
        ledger = row.get("ledger")
        if ledger is None or row.get("usage") is None:
            if (row["outcome"] != "INVALID_ABORT" or row["actual_tokens"] is not None
                    or row["accounting_status"] != "UNRESOLVED" or row["model_calls"] is not None or row["tool_calls"] is not None):
                raise ValueError("unavailable ledger cannot have a valid outcome/cost")
            continue
        accounting = reconcile(row)
        complete = row["outcome"] != "INVALID_ABORT"
        if complete:
            expected_calls = (6, 6) if row["condition"] == CONDITIONS[0] else (1, len(inspection_targets(row["world_id"])) + 1)
            if ((row["model_calls"], row["tool_calls"]) != expected_calls or accounting["call_count"] != sum(expected_calls) or accounting["unknown_calls"]
                    or accounting["reserved_tokens"] or ledger["run"]["status"] != "completed"):
                raise ValueError("incomplete declared calls or unresolved Session accounting")
    groups = {}
    for model in MODELS:
        groups[model] = {}
        for condition in CONDITIONS:
            selected = [r for r in rows if (r["model_id"], r["condition"]) == (model, condition)]
            groups[model][condition] = dict(episodes=len(selected), successes=sum(r["outcome"] == "success" for r in selected),
                failed=sum(r["outcome"] == "failed" for r in selected), invalid=sum(r["outcome"] == "INVALID_ABORT" for r in selected),
                known_tokens=sum(r["actual_tokens"] for r in selected if r["actual_tokens"] is not None),
                model_calls=sum(r["model_calls"] for r in selected if r["model_calls"] is not None),
                tool_calls=sum(r["tool_calls"] for r in selected if r["tool_calls"] is not None),
                unresolved_episodes=sum(r["accounting_status"] != "KNOWN" for r in selected))
    return dict(method_version=METHOD, status="INVALID_ABORT" if any(r["outcome"] == "INVALID_ABORT" for r in rows) else "CAPABILITY_DIAGNOSTIC_COMPLETE",
                counts_toward_verdict=False, groups=groups,
                limitations=["four previously observed worlds", "supplied inspections are not a budget-matched efficacy control",
                             "two sequential local models; no agent-count or hardware scaling claim", "no R4/G5 completion verdict"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "output", "runtime-site", "small-model", "large-model"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("exclusive new output required")
    model_paths = dict(qwen_1_5b=args.small_model, qwen_3b=args.large_model)
    freeze = verified_inputs(args.config, model_paths, args.runtime_site)
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "freeze.json", freeze)
    _, _, LocalModelAdapter = runtime()
    rows, aborted = [], None
    try:
        import torch
        for model_id in MODELS:
            torch.cuda.reset_peak_memory_stats()
            load_started = time.monotonic_ns()
            model = LocalModelAdapter(model_paths[model_id])
            load_elapsed = time.monotonic_ns() - load_started
            model_class = type(model.model.model).__name__
            if model_class != freeze["config"]["model_class"] or model.identity["model_manifest"] != freeze["models"][model_id]:
                raise ValueError("common model class or frozen identity mismatch")
            save(args.output / (model_id + "-identity.json"), dict(model.identity, model_class=model_class,
                load_elapsed_ns=load_elapsed, load_peak_cuda_bytes=torch.cuda.max_memory_allocated(),
                load_current_cuda_bytes=torch.cuda.memory_allocated()))
            for index, world in enumerate(tasks.world_ids()):
                for condition in CONDITIONS[index % 2:] + CONDITIONS[:index % 2]:
                    row = episode(model, freeze["config"], model_id, world, condition,
                                  args.output / f"{model_id}-{index}-{condition}")
                    rows.append(row)
                    print(model_id, world, condition, row["outcome"], row["usage"], flush=True)
                    if row["outcome"] == "INVALID_ABORT":
                        raise RuntimeError(wire(row["error"]))
            del model
            gc.collect()
            torch.cuda.empty_cache()
    except Exception as exc:
        aborted = {"type": type(exc).__name__, "message": str(exc)}
    observed = {(r["model_id"], r["world_id"], r["condition"]) for r in rows}
    for model_id in MODELS:
        for world in tasks.world_ids():
            for condition in CONDITIONS:
                if (model_id, world, condition) not in observed:
                    rows.append(dict(model_id=model_id, world_id=world, condition=condition, outcome="INVALID_ABORT",
                        error={"type": "NotStarted", "cause": aborted}, actual_tokens=None, model_calls=0, tool_calls=0,
                        accounting_status="NOT_STARTED", method_version=METHOD, counts_toward_verdict=False))
    after, hash_errors = {}, []
    for path in freeze["files_sha256"]:
        try:
            after[path] = file_hash(path)
        except OSError as exc:
            after[path] = None
            hash_errors.append({"path": path, "error": str(exc)})
    save(args.output / "after.json", dict(files_sha256=after, unchanged=after == freeze["files_sha256"], errors=hash_errors))
    save(args.output / "episodes.json", rows)
    try:
        summary = summarize(rows)
    except (ValueError, TypeError, KeyError) as exc:
        summary = dict(method_version=METHOD, status="INVALID_ABORT", counts_toward_verdict=False,
                       accounting_summary=None, error={"type": type(exc).__name__, "message": str(exc)})
    if aborted or after != freeze["files_sha256"]:
        summary.update(status="INVALID_ABORT", collection_error=aborted, frozen_inputs_unchanged=after == freeze["files_sha256"])
    save(args.output / "summary.json", summary)
    return 2 if summary["status"] == "INVALID_ABORT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
