"""Experimental logical-agent scaling on one common, external Session runtime.

Tasks and policies live in bench; the runtime remains the sole lease, receipt,
publication and budget owner. The finite study makes no confirmatory verdict.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gc
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time

from . import r4_tasks as tasks
from .r3_framed_pilot import frame

METHOD = "r4_session_scaling_pilot_v1"
COUNTS = (1, 2, 4, 8, 16, 32)
POLICIES = ("private", "blackboard", "dedup_ttl", "versioned")
MODELS = {
    "small": ("Qwen/Qwen2.5-Coder-1.5B-Instruct", "2e1fd397ee46e1388853d2af2c993145b0f1098a"),
    "medium": ("Qwen/Qwen2.5-Coder-3B-Instruct", "488639f1ff808d1d3d0ba301aef8c11461451ec5"),
}
MODEL_MANIFESTS = {
    "small": "600319fcf68b230820502b61767b49ce375316a2d23fe4708126ff5e5fbc26c8",
    "medium": "cf4593f14704152d28ea15c6630ee7abaca52580973524a386e05ba217391777",
}


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def save(path, value):
    with Path(path).open("x") as stream:
        stream.write(wire(value) + "\n")


def configuration():
    conditions = []
    def add(cohort, policy, n, regime):
        conditions.append(dict(id=f"{regime}-{cohort}-{policy}-n{n}", cohort=cohort,
                               policy=policy, agents=n, regime=regime))
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
    return dict(method_version=METHOD, phase="pilot", counts_toward_verdict=False,
                worlds=tasks.world_ids(), conditions=conditions, steps=32, token_cap=65536, binding_token_cap=8192,
                max_calls=64, max_new_tokens=256, context_tokens=2048, context_bytes=32768,
                artifact_bytes=32768, deadline_seconds=30, seed=3109, order_seed=3137,
                models={key: dict(repository=value[0], revision=value[1], precision="float16",
                                  quantization=None, manifest_sha256=MODEL_MANIFESTS[key]) for key, value in MODELS.items()},
                mixed_medium_start_step=28, measurement=dict(confidence=0.95,
                bootstrap_resamples=2000, seed=3141, budget_cap=10000))


def model_for(condition, step):
    cohort = condition["cohort"]
    return "medium" if cohort == "medium" or cohort == "mixed" and step >= 28 else "small"


def episode_token_cap(config, condition):
    return config["binding_token_cap"] if condition["regime"] == "fixed_tokens" else config["token_cap"]


class LocalModels:
    """One resident checkpoint; explicit model replacement is charged in time."""
    def __init__(self, paths):
        self.paths, self.loaded, self.adapter = paths, None, None
        self.loads = []

    def get(self, key):
        if key != self.loaded:
            started = time.monotonic_ns()
            self.close()
            from pheroos_runtime.session_driver_v1 import LocalModelAdapter
            event = dict(model_ref=key, status="INVALID_ABORT")
            try:
                self.adapter = LocalModelAdapter(self.paths[key])
                self.loaded = key
                event.update(status="loaded", identity=deepcopy(self.adapter.identity),
                             model_class=type(self.adapter.model.model).__name__)
                if event["model_class"] != "Qwen2ForCausalLM":
                    raise ValueError("unexpected model class")
            except Exception as error:
                event.update(status="INVALID_ABORT", error=dict(type=type(error).__name__, message=str(error)))
                raise
            finally:
                event["elapsed_ns"] = time.monotonic_ns() - started
                self.loads.append(event)
        return self.adapter

    def close(self):
        if self.adapter is not None:
            torch = self.adapter.model.torch
            self.adapter, self.loaded = None, None
            gc.collect()
            torch.cuda.empty_cache()


class DeadlineReached(Exception):
    pass


def bound_receipt(session, lease, call_id, action, request, response):
    stored = session.call(call_id)
    if ((stored["id"], stored["work_id"], stored["version"], stored["epoch"], stored["action"], stored["state"])
            != (call_id, lease.task_id, lease.version, lease.epoch, action, "received")
            or wire(stored["request"]) != wire(request) or wire(stored["response"]) != wire(response)):
        raise ValueError("raw request/response or lineage differs from durable receipt")
    return stored


def history_record(record):
    """Coordination consumes verified task facts, never hidden-score diagnostics."""
    return {key: deepcopy(record[key]) for key in
            ("id", "world_id", "step", "agent", "task_version", "valid", "feedback",
             "artifact", "origin_identity", "action", "semantic_action", "runtime_artifact_ref")}


def _snapshot_accounting(snapshot):
    if snapshot is None:
        return None
    calls = snapshot["calls"]
    dispatched = {e["lineage"]["call_id"] for e in snapshot["events"]
                  if e["event_type"] == "ext.session.dispatched"}
    accounting = {key: snapshot[key] for key in
                  ("actual_tokens", "reserved_tokens", "unknown_tokens", "unknown_calls")}
    accounting.update(model_calls=sum(c["action"] == "model.generate" and c["id"] in dispatched for c in calls),
                      tool_calls=sum(c["action"] == "tool.evaluate" and c["id"] in dispatched for c in calls),
                      request_bytes=sum(len(c["request"].encode()) for c in calls),
                      response_bytes=sum(json.loads(c["response"])["response_bytes"] if c["state"] == "response_rejected"
                                         else len((c["response"] or "").encode()) for c in calls),
                      event_bytes=sum(len(wire(e).encode()) for e in snapshot["events"]),
                      model_elapsed_ns=sum(json.loads(c["response"]).get("elapsed_ns", 0) for c in calls
                                           if c["action"] == "model.generate" and c["state"] == "received"),
                      monetary_cost=None)
    return accounting


def episode(output, world, condition, config, models, *, clock=time.monotonic_ns):
    from pheroos_runtime.session_v1 import Session
    from pheroos_runtime.session_driver_v1 import SessionDriver, current_authorization
    from pheroos_runtime.store import BudgetExceeded

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    agents = [f"agent{i}" for i in range(condition["agents"])]
    work = [dict(id=f"turn{i}", version=tasks.task_version(world, i),
                 dependencies=[f"turn{i-1}"] if i else [], agents=[agents[i % len(agents)]],
                 actions=["model.generate", "tool.evaluate"]) for i in range(config["steps"])]
    session = None
    records, controls, errors, success_steps = [], [], [], []
    status, reason, snapshot = "complete", "call_limit", None
    started = clock()
    deadline = started + config["deadline_seconds"] * 1_000_000_000 if condition["regime"] == "fixed_deadline" else None
    communication_bytes, trimmed, model_load_ns = 0, 0, 0
    def control(kind, value=None, count=1):
        controls.append(dict(operation=kind, operations=count,
                             bytes=len(wire(value).encode()) if value is not None else 0))
    def authorize(scope, task, version, action, payload):
        if deadline is not None and clock() >= deadline:
            raise DeadlineReached("deadline reached before dispatch/publication")
        result = current_authorization(scope, task, version, action, payload)
        if deadline is not None and clock() >= deadline:
            raise DeadlineReached("deadline reached during current authorization")
        return result
    try:
        session = Session.create(output / "session.sqlite", f"r4-{world}-{condition['id']}",
                                 agents=agents, work=work, token_cap=episode_token_cap(config, condition),
                                 max_calls=config["max_calls"], context_bytes=config["context_bytes"],
                                 artifact_bytes=config["artifact_bytes"])
        control("session.create")
        for step in range(config["steps"]):
            if deadline is not None and clock() >= deadline:
                reason = "deadline"
                break
            agent, version = agents[step % len(agents)], tasks.task_version(world, step)
            history = [history_record(record) for record in records[-32:] if record["published"]]
            selected = tasks.select(condition["policy"], history, agent, step, version)
            control("policy.select", history, count=len(history) + 1)
            for record in selected:
                stored = session.artifact(record["runtime_artifact_ref"])
                control("artifact.read", stored)
                if any(wire(record.get(key)) != wire(value) for key, value in stored["value"].items()):
                    raise ValueError("selected task history differs from the persistent verified artifact")
            key = model_for(condition, step)
            # Driver references must not keep the previous checkpoint resident.
            if "driver" in locals():
                driver.models.clear()
            tick = clock()
            model = models.get(key)
            model_load_ns += clock() - tick
            messages = tasks.messages_for(world, step, selected)
            control("context.encode", messages)
            preflight = []
            while True:
                prompt = model.count_tokens(messages)
                control("model.tokenize", messages)
                preflight.append(dict(prompt_tokens=prompt, messages_sha256=sha256(wire(messages).encode()).hexdigest(),
                                      selected_ids=[r["id"] for r in selected]))
                if type(prompt) is not int or prompt < 1:
                    raise ValueError("adapter returned invalid token count")
                if prompt + config["max_new_tokens"] <= config["context_tokens"]:
                    break
                if not selected:
                    raise ValueError("public task exceeds shared context bound")
                selected = selected[1:]
                trimmed += 1
                messages = tasks.messages_for(world, step, selected)
                control("context.trim", messages)
            communication_bytes += sum(len(wire(r).encode()) for r in selected if r["agent"] != agent)
            lease = session.claim(agent, f"turn{step}", lease_seconds=3600)
            control("session.claim")
            if lease is None:
                raise ValueError("declared ready work could not be claimed")
            session.checkpoint(lease, {"selected_ids": [r["id"] for r in selected]})
            control("session.checkpoint")
            record = dict(id=f"step{step}", step=step, agent=agent, task_version=version,
                          model_ref=key, selected_ids=[r["id"] for r in selected],
                          preflight=preflight,
                          messages=messages, receipt_ids=[], response=None, evaluation=None, valid=False, artifact=None,
                          published=False, feedback="not evaluated", prefix_success=False)
            records.append(record)
            seed = config["seed"] + config["worlds"].index(world) * 100 + step
            driver = SessionDriver(session, models={key: model}, authorization=authorize,
                                   context_tokens=config["context_tokens"])
            # Drop this local reference too before a later model switch.
            del model
            call_id = f"generate-{step}"
            record["receipt_ids"].append(call_id)
            response = driver.generate(lease, call_id, key, messages,
                                       max_new_tokens=config["max_new_tokens"], seed=seed)
            control("model.driver", response)
            expected = dict(task_id=lease.task_id, version=lease.version, model_ref=key,
                            model_identity=driver.models[key].identity, messages=messages,
                            max_new_tokens=config["max_new_tokens"], seed=seed)
            bound = bound_receipt(session, lease, call_id, "model.generate", expected, response)
            control("receipt.binding", bound)
            if response["prompt_tokens"] != prompt:
                raise ValueError("received prompt usage differs from context preflight")
            record["response"] = deepcopy(response)
            if deadline is not None and clock() >= deadline:
                reason = "deadline"
                break  # The known late receipt is charged; it cannot publish.
            text, diagnostic = frame(response.get("text"))
            control("framing", {"raw": response.get("text"), "text": text, "diagnostic": diagnostic},
                    1 + diagnostic["parse_operations"])
            record["framing"] = diagnostic
            arguments = dict(world=world, step=step, memory=selected, text=text)
            def evaluate(args):
                return tasks.apply(args["world"], args["step"], args["memory"], args["text"])
            driver.tools["task.evaluate"] = evaluate
            evaluate_id = f"evaluate-{step}"
            record["receipt_ids"].append(evaluate_id)
            receipt = driver.evaluate(lease, evaluate_id, "task.evaluate", arguments)
            record["evaluation"] = deepcopy(receipt)
            control("tool.driver", receipt)
            tool_request = dict(task_id=lease.task_id, version=lease.version,
                                tool_ref="task.evaluate", arguments=arguments)
            bound = bound_receipt(session, lease, evaluate_id, "tool.evaluate", tool_request, receipt)
            control("receipt.binding", bound)
            checked = receipt["artifact"]
            independent = evaluate(arguments)
            control("tool.verify", independent)
            if wire(checked) != wire(independent):
                raise ValueError("task tool receipt fails independent replay")
            ref = session.publish(lease, evaluate_id, checked,
                                  verify=lambda task, value: task == lease.task_id and wire(value) == wire(independent),
                                  authorize=authorize)
            control("session.publish")
            record.update(deepcopy(checked))
            record.update(published=True, runtime_artifact_ref=ref, elapsed_ns=clock() - started)
        if reason != "call_limit":
            session.cancel()
            control("session.cancel")
    except (DeadlineReached, BudgetExceeded) as error:
        reason = "deadline" if isinstance(error, DeadlineReached) else "budget"
        errors.append(dict(type=type(error).__name__, message=str(error), stage="valid_stop"))
        if session is not None:
            try:
                session.cancel()
                control("session.cancel")
            except Exception as cleanup:
                status = "INVALID_ABORT"
                errors.append(dict(type=type(cleanup).__name__, message=str(cleanup), stage="cleanup"))
    except Exception as error:
        status, reason = "INVALID_ABORT", "runtime_error"
        errors.append(dict(type=type(error).__name__, message=str(error), stage="episode"))
        if session is not None:
            try:
                session.cancel()
                control("session.cancel")
            except Exception as cleanup:
                errors.append(dict(type=type(cleanup).__name__, message=str(cleanup), stage="cleanup"))
    finally:
        if "driver" in locals():
            driver.models.clear()
    if session is not None:
        try:
            snapshot = session.snapshot()
            control("session.snapshot")
        except Exception as error:
            status, reason = "INVALID_ABORT", "snapshot_error"
            errors.append(dict(type=type(error).__name__, message=str(error), stage="snapshot"))
    execution_elapsed = clock() - started
    try:
        accounting = _snapshot_accounting(snapshot)
        if snapshot is not None:
            retained_ids = {call["id"] for call in snapshot["calls"]}
            for record in records:
                record["receipt_ids"] = [key for key in record["receipt_ids"] if key in retained_ids]
    except Exception as error:
        accounting, status, reason = None, "INVALID_ABORT", "accounting_error"
        errors.append(dict(type=type(error).__name__, message=str(error), stage="accounting"))
    completed = [r for r in records if r["published"]]
    # Hidden evaluation occurs only after execution/deadline decisions finish.
    # Outcome-dependent verifier time cannot change later admitted model turns.
    evaluator_started = clock()
    final_step = records[-1]["step"] if records else 0
    success, current_success = None, None
    try:
        for index, record in enumerate(completed):
            record["prefix_success"] = tasks.score(world, record["step"], completed[:index + 1])
            control("evaluator.score")
            if record["prefix_success"]:
                success_steps.append(record["step"])
        if status == "complete":
            success = tasks.score(world, config["steps"] - 1, completed)
            current_success = tasks.score(world, final_step, completed)
            control("evaluator.score", count=2)
    except Exception as error:
        status, reason, success, current_success = "INVALID_ABORT", "evaluator_error", None, None
        errors.append(dict(type=type(error).__name__, message=str(error), stage="evaluator"))
    evaluator_elapsed = clock() - evaluator_started
    if accounting is not None:
        accounting.update(communication_bytes=communication_bytes, elapsed_ns=execution_elapsed,
                          evaluator_elapsed_ns=evaluator_elapsed,
                          model_load_ns=model_load_ns, control_operations=sum(c["operations"] for c in controls),
                          processing_bytes=sum(c["bytes"] for c in controls))
        if accounting["reserved_tokens"] or accounting["unknown_calls"]:
            status, reason = "INVALID_ABORT", "unresolved_runtime"
            success, current_success = None, None
    # Every condition must complete the same final-version objective.
    # Earlier-version success remains a separately labeled diagnostic.
    final_version = tasks.task_version(world, config["steps"] - 1)
    reached = any(r["response"] is not None and r["task_version"] == final_version for r in records)
    row = dict(method_version=METHOD, phase="pilot", counts_toward_verdict=False,
               world_id=world, condition_id=condition["id"], status=status, stop_reason=reason,
               success=success, accounting=accounting, records=records, controls=controls, errors=errors,
               context_trim_count=trimmed, active_agents=len({r["agent"] for r in records if r["response"]}),
               current_snapshot_success=current_success, final_version_reached=reached,
               success_steps=success_steps, final_step=final_step,
               ledger_calls=snapshot.get("calls") if type(snapshot) is dict else None,
               ledger_events=snapshot.get("events") if type(snapshot) is dict else None)
    save(output / "snapshot.json", snapshot)
    save(output / "episode.json", row)
    return row


def hash_file(path):
    value = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def freeze(config_path, model_paths):
    import pheroos
    import pheroos_runtime.session_v1 as runtime
    root = Path(__file__).resolve().parents[2]
    source_paths = [Path(config_path).resolve(), Path(__file__).resolve(),
                    root / "src/pheroos_bench/r4_tasks.py", root / "src/pheroos_bench/r4_measurement.py",
                    root / "R4-session-scaling-v1-contract.md"]
    source_paths += sorted((root / "tests").glob("test_r4_*.py"))
    source_paths += [root / "src/pheroos_bench" / name for name in
                     ("r3_framed_pilot.py", "r3_pilot.py", "r3_tool_pilot.py", "r3_tasks.py", "r3_tool_tasks.py", "r0_measurement.py", "e3_verdict.py")]
    source_paths.append(Path(sys.executable).resolve())
    source_paths += sorted(Path(runtime.__file__).parent.glob("*.py"))
    core = Path(pheroos.__file__).parent
    source_paths += sorted(p for p in core.rglob("*") if p.is_file() and p.suffix in (".py", ".json"))
    manifests = {}
    for key, model_path in model_paths.items():
        path = Path(model_path)
        manifest = json.loads((path / "manifest.json").read_text())
        if hash_file(path / "manifest.json") != MODEL_MANIFESTS[key] or any(wire(manifest.get(field)) != wire(configuration()["models"][key][field])
               for field in ("repository", "revision", "precision", "quantization")):
            raise ValueError("model identity differs from preregistered model")
        if type(manifest.get("sha256")) is not dict or not manifest["sha256"]:
            raise ValueError("model manifest lacks file hashes")
        for name, expected in manifest["sha256"].items():
            target = (path / name).resolve()
            if not target.is_relative_to(path.resolve()) or hash_file(target) != expected:
                raise ValueError("model file differs from its manifest")
        manifests[key] = manifest
        source_paths.append(path / "manifest.json")
    return dict(method_version=METHOD, source_sha256={str(p): hash_file(p) for p in source_paths},
                model_manifests=manifests, config=json.loads(Path(config_path).read_text()),
                interpreter=sys.executable, python=sys.version,
                bench_base_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                source_identity="uncommitted development closure is identified by frozen file hashes",
                packages={name: importlib.metadata.version(name) for name in ("torch", "transformers", "pheroos", "pheroos-runtime")},
                counts_toward_verdict=False)


def execution_order(config):
    """Seeded within-cohort/regime order, independent of model/task outcomes."""
    randomizer, groups = random.Random(config["order_seed"]), {}
    for condition in config["conditions"]:
        groups.setdefault((condition["regime"], condition["cohort"]), []).extend(
            (world, condition) for world in config["worlds"])
    order = []
    for group in groups.values():
        randomizer.shuffle(group)
        order.extend(group)
    return order


def environment():
    data = dict(platform=platform.platform(), kernel=platform.release(), machine=platform.machine(),
                logical_cpus=os.cpu_count(), python=sys.version, interpreter=sys.executable,
                hardware_concurrency=1, paid_api=False, monetary_cost=None)
    query = "name,driver_version,memory.total,memory.used,pstate,power.limit,power.draw,temperature.gpu"
    try:
        data["gpu_query_fields"] = query
        data["gpu_query_csv"] = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            text=True, stderr=subprocess.STDOUT, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as error:
        data["gpu_query_error"] = str(error)
    return data


def uncollected(output, world, condition, cause):
    """Retain interrupted ledgers; unstarted cells never masquerade as free work."""
    snapshot, error = None, dict(cause)
    path = Path(output)
    if (path / "session.sqlite").exists():
        from pheroos_runtime.session_v1 import Session
        try:
            snapshot = Session(path / "session.sqlite").snapshot()
        except Exception as exc:
            error["snapshot_error"] = str(exc)
    return dict(method_version=METHOD, phase="pilot", counts_toward_verdict=False,
                world_id=world, condition_id=condition["id"], status="INVALID_ABORT", success=None,
                stop_reason="uncollected" if snapshot else "not_started", accounting=None,
                ledger_calls=snapshot.get("calls") if type(snapshot) is dict else None,
                ledger_events=snapshot.get("events") if type(snapshot) is dict else None,
                errors=[error], records=[], controls=[])


def run(config_path, output, model_paths):
    from .r4_measurement import summarize
    config = json.loads(Path(config_path).read_text())
    if wire(config) != wire(configuration()):
        raise ValueError("config differs from the declared experimental version")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    frozen = freeze(config_path, model_paths)
    save(output / "freeze.json", frozen)
    save(output / "environment.json", environment())
    models, rows = LocalModels(model_paths), []
    order = execution_order(config)
    save(output / "order.json", [dict(world_id=w, condition_id=c["id"]) for w, c in order])
    abort = None
    try:
        for world, condition in order:
            # Deadline comparisons start with resident weights for both models.
            # Setup is still exported in model-loads.json, outside episode clocks.
            if condition["cohort"] != "mixed":
                models.get(model_for(condition, 0))
            row = episode(output / "episodes" / condition["id"] / world, world, condition, config, models)
            rows.append(row)
            with (output / "episodes.jsonl").open("a") as stream:
                stream.write(wire(row) + "\n")
            print(wire(dict(world=world, condition=condition["id"], status=row["status"], success=row["success"],
                            tokens=row["accounting"]["actual_tokens"] if row["accounting"] else None)), flush=True)
            if row["status"] == "INVALID_ABORT":
                abort = dict(type="EpisodeAborted", world_id=world, condition_id=condition["id"])
                break
    except (Exception, KeyboardInterrupt) as error:
        abort = dict(type=type(error).__name__, message=str(error))
    finally:
        try:
            models.close()
        except Exception as error:
            abort = dict(type=type(error).__name__, message=str(error), stage="model_cleanup", prior_abort=abort)
        try:
            save(output / "model-loads.json", models.loads)
        except Exception as error:
            abort = dict(type=type(error).__name__, message=str(error), stage="model_load_export", prior_abort=abort)
    observed = {(r["world_id"], r["condition_id"]) for r in rows}
    for world, condition in order:
        if (world, condition["id"]) not in observed:
            row = uncollected(output / "episodes" / condition["id"] / world, world, condition,
                              abort or dict(type="IncompleteCollection"))
            rows.append(row)
            with (output / "episodes.jsonl").open("a") as stream:
                stream.write(wire(row) + "\n")
    try:
        after = freeze(config_path, model_paths)
        if wire(after) != wire(frozen):
            save(output / "source-drift.json", after)
            abort = dict(type="FrozenSourceChanged")
    except Exception as error:
        abort = dict(type=type(error).__name__, message=str(error), stage="post_collection_freeze")
    try:
        summary = summarize(rows, config)
    except Exception as error:
        summary = dict(status="INVALID_ABORT", counts_toward_verdict=False,
                       measurement_error=dict(type=type(error).__name__, message=str(error)),
                       source_records_retained=len(rows))
    if abort:
        summary.update(status="INVALID_ABORT", collection_abort=abort)
    save(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--small-model", type=Path, required=True)
    parser.add_argument("--medium-model", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.config, args.output, dict(small=args.small_model, medium=args.medium_model))
    return 0 if summary["status"] != "INVALID_ABORT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
