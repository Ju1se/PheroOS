"""Additive, CPU-only replay audit of the completed Session capability pilot."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from pheroos.kernel import RuntimeScope
from pheroos_runtime.authority import authorize, authorize_r3
from pheroos_bench import r3_tasks as base, r3_tool_tasks as tasks

METHOD = "r3_session_capability_v1"
MODELS = ("qwen_1_5b", "qwen_3b")
CONDITIONS = ("autonomous_single", "supplied_current_inspections")
WORLDS = ("code_repair/clamp", "code_repair/chunk_count", "evidence_revision/dispatch_limit", "evidence_revision/channel_route")
REVISIONS = ("2e1fd397ee46e1388853d2af2c993145b0f1098a", "488639f1ff808d1d3d0ba301aef8c11461451ec5")


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(wire(value).encode()).hexdigest()


def check(value, message):
    if not value:
        raise ValueError(message)


def count(value):
    check(type(value) is int and value >= 0, "exact nonnegative integer required")
    return value


def file_hash(path):
    result = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=base._object, parse_constant=base._nonfinite)


def equal(left, right, message):
    check(wire(left) == wire(right), message)


def version(world, step):
    return base.public_view(world, 0 if step < 3 else 2)["task_version"]


def targets(world):
    public = base.public_view(world, 2)
    return ([test["name"] for test in public["visible_tests"]] if world.startswith("code_repair/")
            else [document["source_id"] for document in public["documents"]])


def framing(text):
    check(type(text) is str and len(text) <= 16384, "unexpected unbounded/nontext response")
    body = text.strip(" \t\r\n")
    fenced = body.startswith("```json\n") and body.endswith("\n```")
    if fenced:
        inner = body[8:-4]
        fenced = re.search(r"(?m)^[ \t]*```", inner) is None
        if fenced:
            body = inner
    diagnostic = dict(parse_operations=1, parse_bytes=len(body.encode()))
    try:
        parsed = json.loads(body, object_pairs_hook=base._object, parse_constant=base._nonfinite)
        check(type(parsed) is dict, "action JSON must be an object")
    except (ValueError, TypeError, RecursionError) as exc:
        return text, dict(admitted=False, kind="rejected", reason=str(exc), **diagnostic)
    return body, dict(admitted=True, kind="sole_json_fence" if fenced else "bare_json", reason=None, **diagnostic)


def event(kind, work, lineage):
    return dict(event_type="ext.session." + kind, protocol_id="session.v1", target=work or "run", reason=kind, lineage=lineage)


def database(path, saved):
    # Never use Session.snapshot(): its transaction starts BEGIN IMMEDIATE.
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        db.row_factory = sqlite3.Row
        check(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity check failed")
        for table in ("run", "work", "calls", "artifacts"):
            actual = [dict(row) for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid")]
            equal(actual[0] if table == "run" else actual, saved[table], "SQLite/export mismatch: " + table)
        equal([json.loads(row[0]) for row in db.execute("SELECT value FROM events ORDER BY seq")], saved["events"], "SQLite trace mismatch")
        for table in ("checkpoints", "mailbox"):
            check(db.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0, "undeclared capability diagnostic state")


def freeze_inputs(output):
    freeze, after = read(output / "freeze.json"), read(output / "after.json")
    check(freeze["counts_toward_verdict"] is False and freeze["frozen_before_model_loading"] is True, "invalid pilot freeze")
    config = freeze["config"]
    equal(list(config["models"]), list(MODELS), "model declaration changed")
    equal(config["worlds"], list(WORLDS), "task grid changed")
    equal(config["conditions"], list(CONDITIONS), "conditions changed")
    for key, expected in {"method_version": METHOD, "phase": "capability_diagnostic", "counts_toward_verdict": False,
                          "steps": 6, "diagnostic_step": 5, "max_new_tokens": 256, "context_tokens": 2048,
                          "context_bytes": 65536, "artifact_bytes": 65536, "episode_token_cap": 12288,
                          "max_calls": 16, "seed": 2081, "precision": "float16", "quantization": None,
                          "model_class": "Qwen2ForCausalLM"}.items():
        equal(config[key], expected, "declared configuration changed: " + key)
    equal(after["files_sha256"], freeze["files_sha256"], "recorded post-collection input changes")
    check(after["unchanged"] is True and after["errors"] == [], "post-collection verification failed")
    for path, expected in freeze["files_sha256"].items():
        check(file_hash(path) == expected, "frozen file currently differs: " + path)
    import pheroos_runtime, pheroos
    check(str(Path(pheroos_runtime.__file__).parent) == freeze["environment"]["runtime_root"], "wrong installed runtime import")
    for module in (base, tasks, pheroos_runtime, pheroos):
        check(str(Path(module.__file__).resolve()) in freeze["files_sha256"], "unfrozen imported module")
    for name, expected in freeze["environment"]["packages"].items():
        check(importlib.metadata.version(name) == expected, "installed package version changed")
    check(sys.version == freeze["environment"]["python"], "interpreter identity changed")
    from transformers import AutoTokenizer
    tokenizers, identities, model_paths = {}, {}, {}
    for index, model in enumerate(MODELS):
        manifest = freeze["models"][model]
        check(manifest["revision"] == REVISIONS[index], "unexpected model revision")
        check(manifest["repository"] == ("Qwen/Qwen2.5-Coder-1.5B-Instruct", "Qwen/Qwen2.5-Coder-3B-Instruct")[index], "unexpected model repository")
        check(manifest["precision"] == "float16" and manifest["quantization"] is None, "model precision differs")
        paths = [Path(path).parent for path in freeze["files_sha256"] if path.endswith("/manifest.json") and read(path) == manifest]
        check(len(paths) == 1, "model manifest path is ambiguous")
        root = paths[0]
        check(file_hash(root / "manifest.json") == config["models"][model]["manifest_sha256"], "model manifest raw hash differs")
        for relative, expected in manifest["sha256"].items():
            check(freeze["files_sha256"].get(str(root / relative)) == expected, "missing model member freeze")
        check(sum((root / name).stat().st_size for name in manifest["sha256"]) == manifest["size_bytes"], "model byte total differs")
        identity = read(output / (model + "-identity.json"))
        equal(identity["model_manifest"], manifest, "loaded model differs")
        check(identity["model_class"] == "Qwen2ForCausalLM" and identity["dtype"] == "float16", "common loaded class/precision differs")
        for name in ("load_elapsed_ns", "load_peak_cuda_bytes", "load_current_cuda_bytes"):
            count(identity[name])
        tokenizers[model] = AutoTokenizer.from_pretrained(root, local_files_only=True, trust_remote_code=False)
        identities[model], model_paths[model] = identity, str(root)
    for name in ("cuda", "dtype", "gpu", "torch", "transformers", "python", "model_class"):
        equal(identities[MODELS[0]][name], identities[MODELS[1]][name], "common runtime/model-class control differs")
    return freeze, tokenizers, identities, model_paths


def audit_episode(output, row, tokenizer, identity):
    model, world, condition = row["model_id"], row["world_id"], row["condition"]
    name = f"{model}-{WORLDS.index(world)}-{condition}"
    directory, ledger = output / name, row["ledger"]
    equal(read(directory / "episode.json"), row, "episode file differs from grid export")
    database(directory / "session.sqlite", ledger)
    check(row["method_version"] == METHOD and row["counts_toward_verdict"] is False and row["phase"] == "capability_diagnostic", "episode metadata changed")
    check(row["error"] is None and row["accounting_status"] == "KNOWN", "episode did not finish with known accounting")
    run = ledger["run"]
    equal(run, dict(id=1, run_id=name, status="completed", generation=0, enabled=1,
                    agents='["agent0"]', limits=wire(dict(token_cap=12288, max_calls=16, context_bytes=65536,
                        artifact_bytes=65536, mailbox_bytes=4096, mailbox_messages=16))), "run/common limits differ")
    declared_targets = targets(world) if condition == CONDITIONS[1] else []
    schedule = [(f"inspect-{i}", 5, target) for i, target in enumerate(declared_targets)]
    schedule += [(f"turn-{step}", step, None) for step in ([5] if declared_targets else range(6))]
    check(len(row["turns"]) == len(schedule) == len(ledger["work"]) == len(ledger["artifacts"]), "declared work/publication count differs")
    trace = [event("created", "", dict(run_id=name, limits=json.loads(run["limits"])))]
    records, observed_calls, outcomes = [], [], []
    total_input, total_output, model_calls, prompt_checks, invalid_tokens = 0, 0, 0, 0, 0
    clean_identity = {key: value for key, value in identity.items() if not key.startswith("load_") and key != "model_class"}
    for index, ((work, step, target), turn) in enumerate(zip(schedule, row["turns"])):
        current = version(world, step)
        equal((turn["work_id"], turn["step"], turn["inspection_target"]), (work, step, target), "global turn/index changed")
        declaration = dict(id=work, version=current, agents=["agent0"], actions=["model.generate", "tool.evaluate"],
                           dependencies=[schedule[index - 1][0]] if index else [])
        equal(ledger["work"][index], dict(id=work, version=current, declaration=wire(declaration), status="done",
              owner=None, epoch=1, expires=None, generation=0), "work/lease/dependency declaration changed")
        trace.append(event("claimed", work, dict(task_id=work, version=current, owner="agent0", epoch=1)))
        scope = RuntimeScope("session-v1", name, work)
        memory = deepcopy(records if declared_targets else [r for r in records if r["step"] < step][-6:])
        current_calls = []
        if target is None:
            dropped, preflight = [], []
            while True:
                messages = tasks.messages_for(world, step, memory)
                prompt = len(tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=True))
                preflight.append(dict(prompt_tokens=prompt, messages_sha256=digest(messages), request_bytes=len(wire(messages).encode())))
                prompt_checks += 1
                if prompt + 256 <= 2048:
                    break
                check(not declared_targets and memory, "unrecorded context violation")
                dropped.append(memory.pop(0)["id"])
            equal([{k: v for k, v in attempt.items() if k != "elapsed_ns"} for attempt in turn["context_preflight"]], preflight, "tokenizer/context preflight differs")
            for attempt in turn["context_preflight"]:
                count(attempt["elapsed_ns"])
            equal(turn["dropped_ids"], dropped, "whole-receipt eviction differs")
            request = dict(task_id=work, version=current, model_ref=model, model_identity=clean_identity,
                           messages=messages, max_new_tokens=256, seed=2081 + WORLDS.index(world) * 100 + step)
            response = turn["response"]
            check(response["prompt_tokens"] == prompt and response["model_ref"] == model, "generation usage/model binding differs")
            for field in ("prompt_tokens", "completion_tokens", "elapsed_ns", "peak_cuda_bytes", "adapter_elapsed_ns"):
                count(response[field])
            check(response["completion_tokens"] <= 256, "generation exceeds output bound")
            text, diagnostic = framing(response["text"])
            equal(turn["framing"], diagnostic, "raw framing differs")
            current_calls.append(("model", "model.generate", request, response, prompt, 256))
            model_calls += 1
        else:
            check(turn["response"] is None and "model_call" not in turn, "hidden preload model call")
            equal(turn["context_preflight"], [], "preload tokenizer work invented")
            equal(turn["dropped_ids"], [], "preload history was evicted")
            equal(turn["framing"], dict(kind="declared_inspection", admitted=True), "preload framing differs")
            text = wire(dict(action="inspect", target=target))
        equal(turn["consumed_ids"], [item["id"] for item in memory], "visible receipt ancestry differs")
        arguments = dict(world=world, step=step, memory=memory, text=text)
        result = tasks.apply(world, step, memory, text)
        fact = dict(kind="r3_evaluation_fact_v1", input_digest=digest(arguments), world_id=world, step=step, result=result)
        response = turn["evaluation_response"]
        equal(response["artifact"], fact, "original public evaluator replay differs")
        check(response["tool_ref"] == "evaluate_action" and count(response["prompt_tokens"]) == count(response["completion_tokens"]) == 0, "pure tool usage/capability differs")
        count(response["adapter_elapsed_ns"])
        current_calls.append(("tool", "tool.evaluate", dict(task_id=work, version=current, tool_ref="evaluate_action", arguments=arguments), response, 0, 0))
        for kind, action, request, response, prompt, maximum in current_calls:
            call = ledger["calls"][len(observed_calls)]
            call_id = work + ":" + kind
            authority = (authorize if action == "tool.evaluate" else authorize_r3)(scope, work, current, action, request)
            actual = count(response["prompt_tokens"]) + count(response["completion_tokens"])
            expected = dict(id=call_id, work_id=work, version=current, epoch=1, action=action, request=wire(request), state="received",
                            prompt=prompt, maximum=maximum, reserved=prompt + maximum, response=wire(response), actual=actual, authority=wire(authority))
            equal(call, expected, "durable request/receipt/authority differs")
            equal(turn[kind + "_call"], dict(expected, request=request, response=response), "raw turn receipt differs from SQLite")
            check(len(call["request"].encode()) <= 65536 and len(call["response"].encode()) <= 65536, "wire bound exceeded")
            trace.extend([event("reserved", work, dict(call_id=call_id, tokens=prompt + maximum)),
                          event("dispatched", work, dict(call_id=call_id, authority=authority)),
                          event("received", work, dict(call_id=call_id, actual_tokens=actual, response_digest=digest(response)))])
            observed_calls.append(call_id)
            total_input += response["prompt_tokens"]
            total_output += response["completion_tokens"]
            if kind == "model" and not result["valid"]:
                invalid_tokens += actual
        count(turn["verification_elapsed_ns"])
        check(turn["verification_recomputations"] == 1, "verifier invocation accounting differs")
        payload = dict(task_id=work, version=current, artifact=fact, call_id=work + ":tool",
                       response_digest=digest(turn["evaluation_response"]), scope_ref=scope.scope_ref)
        authority = authorize_r3(scope, work, current, "artifact.publish", payload)
        reference = "sha256:" + digest(payload)
        artifact = dict(ref=reference, work_id=work, version=current, publisher="agent0", value=wire(fact),
                        call_id=work + ":tool", response_digest=payload["response_digest"], authority=wire(authority))
        equal(ledger["artifacts"][index], artifact, "publication is not bound to exactly verified tool receipt")
        equal(turn["publication"], dict(artifact, value=fact, authority=authority, scope_ref=scope.scope_ref), "publication readback differs")
        trace.append(event("published", work, dict(artifact_ref=reference, call_id=work + ":tool", version=current,
                           response_digest=payload["response_digest"], authority=authority)))
        records.append(dict(id=reference, agent="agent0", step=step, task_version=current,
                            **{key: result[key] for key in ("valid", "feedback", "artifact", "action", "semantic_action")},
                            receipt_digest=digest(result["artifact"])))
        outcomes.append(dict(step=step, preparation=target is not None, valid=result["valid"], action=result["action"],
                             feedback=result["feedback"], semantic_action=result["semantic_action"],
                             model_tokens=0 if target is not None else turn["model_call"]["actual"]))
    equal(ledger["events"], trace, "exact causal lifecycle trace differs")
    equal(row["records"], records, "published task history differs")
    check(len(observed_calls) == len(set(observed_calls)) == len(ledger["calls"]), "extra/duplicate hidden calls")
    selected = [r for r in records if r["valid"] is True and r["task_version"] == version(world, 5)
                and r["artifact"]["kind"] == "submitted_candidate"]
    success = False
    if selected:
        candidate = selected[-1]["artifact"]["receipt"]["candidate"]
        normalized = dict(code="\n".join(candidate["code_lines"])) if world.startswith("code_repair/") else candidate
        success = base.verify(world, 2, wire(normalized), final=True)["valid"]
    equal(row["outcome"], "success" if success else "failed", "independent final task score differs")
    check(success == tasks.score(world, 5, records), "original final selector disagrees")
    total = total_input + total_output
    for field, expected in dict(actual_tokens=total, reserved_tokens=0, unknown_tokens=0, unknown_calls=0, call_count=len(observed_calls)).items():
        check(count(ledger[field]) == expected, "ledger accounting differs: " + field)
    check(total <= 12288 and len(observed_calls) <= 16, "common budget exceeded")
    equal(row["usage"], dict(input_tokens=total_input, output_tokens=total_output), "token component accounting differs")
    check(count(row["actual_tokens"]) == total and count(row["model_calls"]) == model_calls and count(row["tool_calls"]) == len(schedule), "logical model/tool accounting differs")
    for field, expected in dict(request_bytes=sum(len(c["request"].encode()) for c in ledger["calls"]),
        response_bytes=sum(len(c["response"].encode()) for c in ledger["calls"]),
        retained_response_bytes=sum(len(c["response"].encode()) for c in ledger["calls"]), trace_bytes=sum(len(wire(e).encode()) for e in trace)).items():
        check(count(row[field]) == expected, "JSON byte accounting differs")
    return dict(model_id=model, world_id=world, condition=condition, outcome=row["outcome"], actual_tokens=total,
                input_tokens=total_input, output_tokens=total_output, model_calls=model_calls, tool_calls=len(schedule),
                public_invalid_model_tokens=invalid_tokens, tokenizer_checks=prompt_checks,
                authority_checks=len(observed_calls) + len(schedule), events=len(trace), actions=outcomes)


def audit(output):
    evidence_paths = [output / name for name in ("freeze.json", "after.json", "episodes.json", "summary.json")]
    evidence_paths += sorted(output.glob("*-identity.json")) + sorted(output.glob("*/episode.json")) + sorted(output.glob("*/session.sqlite"))
    evidence_before = {str(p.resolve()): file_hash(p) for p in evidence_paths}
    freeze, tokenizers, identities, model_paths = freeze_inputs(output)
    rows = read(output / "episodes.json")
    expected = [(model, world, condition) for model in MODELS for index, world in enumerate(WORLDS)
                for condition in CONDITIONS[index % 2:] + CONDITIONS[:index % 2]]
    equal([(r["model_id"], r["world_id"], r["condition"]) for r in rows], expected, "full grid/order differs")
    checked = []
    for row in rows:
        checked.append(audit_episode(output, row, tokenizers[row["model_id"]], identities[row["model_id"]]))
        print("verified", row["model_id"], row["world_id"], row["condition"], flush=True)
    groups = {model: {} for model in MODELS}
    for model in MODELS:
        for condition in CONDITIONS:
            selected = [r for r in checked if (r["model_id"], r["condition"]) == (model, condition)]
            groups[model][condition] = dict(episodes=4, successes=sum(r["outcome"] == "success" for r in selected),
                failed=sum(r["outcome"] == "failed" for r in selected), invalid=0,
                known_tokens=sum(r["actual_tokens"] for r in selected), model_calls=sum(r["model_calls"] for r in selected),
                tool_calls=sum(r["tool_calls"] for r in selected), unresolved_episodes=0)
    summary = read(output / "summary.json")
    equal(summary["groups"], groups, "original summary groups differ")
    check(summary["status"] == "CAPABILITY_DIAGNOSTIC_COMPLETE" and summary["counts_toward_verdict"] is False and summary["method_version"] == METHOD, "summary classification differs")
    equal({str(p.resolve()): file_hash(p) for p in evidence_paths}, evidence_before, "audit changed original evidence")
    totals = {key: sum(r[key] for r in checked) for key in ("actual_tokens", "input_tokens", "output_tokens", "model_calls", "tool_calls", "public_invalid_model_tokens", "tokenizer_checks", "authority_checks", "events")}
    totals.update(episodes=16, invalid_aborts=0, unknown_calls=0, unknown_tokens=0, reserved_tokens=0,
                  failed_episode_tokens=sum(r["actual_tokens"] for r in checked if r["outcome"] == "failed"))
    return dict(audit_method="r3_session_capability_independent_audit_v1", status="AUDIT_PASS",
        created_utc=datetime.now(timezone.utc).isoformat(), counts_toward_verdict=False, generated_model_calls=0,
        original_evidence_unchanged=True, frozen_files_checked=len(freeze["files_sha256"]),
        frozen_core_json_contracts_checked=sum('/pheroos/' in p and p.endswith('.json') for p in freeze["files_sha256"]),
        frozen_input_hashes=freeze["files_sha256"], source_config=freeze["config"], model_paths=model_paths, model_identities=identities,
        evidence_sha256=evidence_before, audit_source_sha256={str(Path(__file__).resolve()): file_hash(__file__)},
        environment=freeze["environment"], current_heads={name: subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True).strip()
             for name, path in (("bench_core", str(Path(__file__).resolve().parents[2])), ("external_runtime", "/home/scott/projects/PheroOS-runtime"))},
        groups=groups, totals=totals, episode_checks=checked,
        logical_bytes={key: sum(r[key] for r in rows) for key in ("request_bytes", "response_bytes", "retained_response_bytes", "trace_bytes")},
        g5_gate_recommendation="ENGINEERING_PASS_NEGATIVE_EFFICACY_NO_PROMOTION",
        limitations=["Four previously observed worlds and one seed: no confirmatory or held-out evidence.",
          "Supplied inspections are a preparation diagnostic, not a budget-matched efficacy control or forced-submission reasoning test.",
          "Both models used one GPU sequentially; concurrent CPU work makes timings descriptive, not isolated latency/throughput evidence.",
          "Completion token IDs were not stored: completion counts reconcile to durable receipts and frozen tensor-length implementation, not independent text retokenization.",
          "Fresh public-core authority projections and exact causal trace replay are checked; recorded projections never become reusable permissions.",
          "Trusted-host development authority, cancellation/fault acceptance and multi-agent efficacy remain separate from this successful single-agent engineering audit."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="completed immutable collection directory")
    parser.add_argument("--audit-output", type=Path, required=True, help="new exclusive additive JSON receipt")
    args = parser.parse_args()
    check(not args.audit_output.exists(), "audit output already exists")
    try:
        result = audit(args.output.resolve())
    except Exception as exc:
        result = dict(audit_method="r3_session_capability_independent_audit_v1", status="INVALID_ABORT", counts_toward_verdict=False,
                      generated_model_calls=0, error=dict(type=type(exc).__name__, message=str(exc)))
    with args.audit_output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["status"], result.get("totals", result.get("error")), flush=True)
    return 0 if result["status"] == "AUDIT_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
