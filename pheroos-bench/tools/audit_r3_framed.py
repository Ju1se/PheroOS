"""Additive, offline audit of frozen R3 v3; never generates model responses.

Reuses independent v2 audit helpers where the task/ledger contract is identical.
V3 framing and processing/transport counters are independently reconstructed.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import re

from pheroos.kernel import RuntimeScope
from pheroos_runtime.authority import authorize_r3
from pheroos_bench import r3_framed_pilot as pilot, r3_tasks, r3_tool_tasks as tasks
import audit_r3_tool_pilot as previous
from audit_r3_tool_pilot import (
    ARMS, WORLDS, canonical, check, read_lines, file_hash, source_version, agent_for,
    select_memory, record_for, check_context, check_database, usage, classify_pair, score,
)

METHOD = "r3_framed_action_pilot_v3"
EXTRAS = {"raw_text", "framing", "processing_cost", "raw_reply_sha256"}
REQUEST_FIELDS = ("task_id", "version", "call_id", "messages", "max_new_tokens", "seed")


def wire_size(value):
    return len(canonical(value).encode())


def raw_response(row):
    response = row["response"]
    return {key: response["raw_text"] if key == "text" else value
            for key, value in response.items() if key not in EXTRAS}


def check_framing(row):
    response = row["response"]
    raw = raw_response(row)
    check(sha256(canonical(raw).encode()).hexdigest() == response["raw_reply_sha256"], "raw reply hash mismatch")
    text = raw["text"]
    body = text.strip(" \t\r\n")
    framed = body.startswith("```json\n") and body.endswith("\n```")
    if framed:
        inner = body[len("```json\n"):-len("\n```")]
        framed = re.search(r"(?m)^[ \t]*```", inner) is None
        if framed:
            body = inner
    # This completed pilot has no parsing failures. Refuse to silently count a
    # different contract as an admission if the raw data no longer reproduces.
    parsed = json.loads(body, object_pairs_hook=r3_tasks._object, parse_constant=r3_tasks._nonfinite)
    check(type(parsed) is dict and len(text) <= 16384, "unexpected non-admitted raw response")
    diagnostic = dict(admitted=True, kind="sole_json_fence" if framed else "bare_json", reason=None,
                      parse_operations=1, parse_bytes=len(body.encode()))
    check(response["text"] == body and response["framing"] == diagnostic, "framing view/diagnostic mismatch")
    receipt = {key: value for key, value in raw.items() if key not in ("authority", "ledger")}
    payload = {key: row["request"][key] for key in REQUEST_FIELDS}
    matching = [call for call in raw["ledger"]["calls"] if call["id"] == row["request"]["call_id"]]
    check(len(matching) == 1 and matching[0]["state"] == "received", "missing raw durable receipt")
    check(canonical(matching[0]["request"]) == canonical(payload) and
          canonical(matching[0]["response"]) == canonical(receipt), "raw receipt request/response binding mismatch")
    counters = dict(response_copy_operations=1, response_copy_bytes=wire_size(raw),
                    frame_read_operations=1, frame_read_bytes=wire_size(text),
                    json_parse_operations=1, json_parse_bytes=len(body.encode()),
                    frame_write_operations=1, frame_write_bytes=wire_size(body) + wire_size(diagnostic),
                    receipt_check_operations=1,
                    receipt_check_bytes=wire_size(receipt) + wire_size(matching) + wire_size(payload))
    counters["total_operations"] = sum(value for key, value in counters.items() if key.endswith("_operations"))
    counters["total_bytes"] = sum(value for key, value in counters.items() if key.endswith("_bytes"))
    check(response["processing_cost"] == counters, "processing operation/byte counters mismatch")


def check_ledger(snapshot, rows, cap, max_calls):
    raw_rows = [dict(row, response=raw_response(row)) for row in rows]
    previous.check_ledger(snapshot, raw_rows, cap, max_calls)


def check_episode_accounting(episode, main, probes):
    transport = []
    def entry(request, response):
        transport.append(dict(request_bytes=wire_size(request), response_bytes=wire_size(response),
                              operation=request["op"], response_received=True))
    def call(row):
        for item in row["context_preflight"]:
            entry(item["request"], item["response"])
        entry(row["request"], raw_response(row))
        if row["publication_request"]:
            entry(row["publication_request"], row["publication"])
    by_step = {row["step"]: row for row in probes}
    for row in main:
        call(row)
        if row["step"] in by_step:
            call(by_step[row["step"]])
    for kind, rows in (("main", main), ("probe", probes)):
        request = {key: rows[-1]["request"][key] for key in ("ledger_path", "token_cap", "max_calls")}
        entry(dict(request, op="ledger"), episode[kind + "_ledger"])
        parser = dict(received=len(rows), admitted=sum(row["response"]["framing"]["admitted"] for row in rows),
                      public_valid_actions=sum(row["result"]["valid"] for row in rows))
        check(episode[kind + "_parser"] == parser, "episode parser/valid-action counters mismatch")
    check(episode["transport_accounting"] == transport, "ordered raw transport records mismatch")
    check(episode["transport_bytes"] == sum(row["request_bytes"] + row["response_bytes"] for row in transport), "transport bytes mismatch")
    rows = main + probes
    check(episode["serialized_trace_bytes"] == sum(wire_size(row) + 1 for row in rows), "serialized trace bytes mismatch")
    for unit in ("operations", "bytes"):
        check(episode["processing_" + unit] == sum(row["response"]["processing_cost"]["total_" + unit] for row in rows),
              "episode processing total mismatch")


def verify_freeze(output, model_path):
    check((output / "summary.json").is_file() and not (output / "abort.json").exists(), "incomplete/aborted pilot")
    freeze = json.loads((output / "freeze.json").read_text())
    check(freeze["method_version"] == METHOD and freeze["counts_toward_verdict"] is False
          and freeze["frozen_before_calls"] is True and freeze["config"] == pilot.configuration(), "invalid freeze/config")
    for path, digest in freeze["source_sha256"].items():
        check(file_hash(Path(path)) == digest, "frozen source mismatch: " + path)
    for name, files in freeze["installed"]["files"].items():
        for item in files.values():
            check(file_hash(Path(item["path"])) == item["sha256"], "installed artifact mismatch: " + item["path"])
    for name, version in freeze["installed"]["packages"].items():
        check(importlib.metadata.version(name) == version, "installed dependency version changed: " + name)
    for path, digest in freeze["bench_process"]["core_files"].items():
        check(file_hash(Path(path)) == digest, "bench core import mismatch: " + path)
    for module in (pilot, tasks, r3_tasks):
        check(freeze["source_sha256"].get(str(Path(module.__file__).resolve())) == file_hash(Path(module.__file__)),
              "audit imported an unfrozen task/runner")
    manifest = json.loads((model_path / "manifest.json").read_text())
    check(manifest == freeze["model"] and pilot.digest(manifest) == pilot.MODEL_MANIFEST_SHA256, "model identity differs")
    for name, digest in manifest["sha256"].items():
        check(file_hash(model_path / name) == digest, "model bytes differ: " + name)
    environment = json.loads((output / "environment.json").read_text())
    check(environment["model_manifest"] == manifest, "loaded model manifest mismatch")
    check(environment["torch"] == freeze["installed"]["packages"]["torch"] and
          environment["transformers"] == freeze["installed"]["packages"]["transformers"], "loaded package identity mismatch")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
    installed_count = sum(name.startswith("pheroos_runtime/") and name.endswith(".py")
                          for name in freeze["installed"]["files"]["pheroos-runtime"])
    return freeze, manifest, installed_count, tokenizer


def additional_report(output, episodes, calls, freeze, context_path):
    context = json.loads(context_path.read_text())
    by_kind = {kind: [row for row in calls if (":probe:" in row["request"]["call_id"]) == (kind == "probe")]
               for kind in ("main", "probe")}
    costs = {key: sum(row[key] for row in episodes) for key in
             ("processing_operations", "processing_bytes", "transport_bytes", "serialized_trace_bytes", "tool_receipt_bytes")}
    return dict(
        audit_method="r3_framed_independent_audit_v1", source_config=freeze["config"],
        environment=json.loads((output / "environment.json").read_text()),
        installed_artifacts_checked=sum(len(files) for files in freeze["installed"]["files"].values()),
        bench_core_files_checked=len(freeze["bench_process"]["core_files"]),
        parser_admissions=sum(row["response"]["framing"]["admitted"] for row in calls),
        framing_kinds=dict(Counter(row["response"]["framing"]["kind"] for row in calls)),
        valid_actions_by_kind={kind: dict(Counter(row["result"]["action"] for row in rows if row["result"]["valid"]))
                               for kind, rows in by_kind.items()},
        successes_by_world={world: sum(row["outcome"] == "success" for row in episodes if row["world_id"] == world)
                            for world in WORLDS},
        costs=costs, unknown_tokens=0, reserved_tokens=0,
        peak_cuda_bytes=max(row["peak_cuda_bytes"] for row in episodes),
        cpu_acceptance_context=dict(path=str(context_path.resolve()), sha256=file_hash(context_path), receipt=context),
        evidence_file_mtime_utc={name: datetime.fromtimestamp((output / name).stat().st_mtime, timezone.utc).isoformat()
                                 for name in ("freeze.json", "trace.jsonl", "summary.json")},
        by_arm=json.loads((output / "summary.json").read_text())["arms"],
        timing_limitation="CPU wheel/sdist acceptance overlapped this GPU pilot. All wall/GPU elapsed times are descriptive; this is not an isolated throughput or latency comparison.")


def check_call(row, memory, is_probe, checked_ids):
    world, step = row["world_id"], row["step"]
    request, response = row["request"], row["response"]
    check(row["status"] == "received" and response is not None, "unacknowledged/aborted model call")
    check(request["call_id"] not in checked_ids, "duplicate model call ID")
    checked_ids.add(request["call_id"])
    suffix = "-probe" if is_probe else ""
    check(request["scope"] == RuntimeScope("r3-framed-pilot-v3", row["episode_id"] + suffix, "episode").to_dict(),
          "wrong main/probe scope")
    check(request["op"] == "generate" and request["task_id"] == world and
          request["version"] == source_version(world, step), "generation target/version mismatch")
    expected_id = f"{row['episode_id']}:{'probe:' if is_probe else ''}{step}"
    check(request["call_id"] == expected_id, "generation call ID mismatch")
    check(Path(request["ledger_path"]).name == row["episode_id"] + suffix + ".sqlite", "wrong ledger path")
    check(request["max_calls"] == (2 if is_probe else 6) and
          request["token_cap"] == (4096 if is_probe else 12288), "wrong branch budget")
    check(request["seed"] == 1073 + WORLDS.index(world) * 100 + step, "wrong paired generation seed")
    check(request["max_new_tokens"] == 256, "wrong output cap")
    check(all(type(response[k]) is int and response[k] >= 0 for k in
              ("prompt_tokens", "completion_tokens", "elapsed_ns", "peak_cuda_bytes")), "invalid generation metrics")
    check(0 < response["prompt_tokens"] and response["completion_tokens"] <= 256 and
          response["prompt_tokens"] + 256 <= 2048, "generation context/output bound violated")
    check_framing(row)
    expected_result = tasks.apply(world, step, memory, response["text"])
    check(row["result"] == expected_result, "tool action/verifier receipt mismatch")
    scope = RuntimeScope.from_dict(request["scope"])
    payload = {k: request[k] for k in ("task_id", "version", "call_id", "messages", "max_new_tokens", "seed")}
    check(response["authority"] == authorize_r3(scope, world, request["version"], "model.generate", payload),
          "generation authority mismatch")
    if expected_result["valid"]:
        publication = dict(op="publish", scope=request["scope"], task_id=world, version=request["version"],
                           artifact=expected_result["artifact"],
                           verification={k: expected_result[k] for k in ("valid", "feedback", "artifact")})
        check(row["publication_request"] == publication, "publication payload mismatch")
        payload = {k: publication[k] for k in ("task_id", "version", "artifact", "verification")}
        check(row["publication"] == {"authority": authorize_r3(scope, world, request["version"], "artifact.publish", payload)},
              "publication authority mismatch")
        return 2
    check(row["publication"] is None and row["publication_request"] is None, "invalid action was published")
    return 1



def audit(output, model_path, context_path):
    freeze, manifest, installed_count, tokenizer = verify_freeze(output, model_path)
    episodes = read_lines(output / "episodes.jsonl")
    traces = read_lines(output / "trace.jsonl")
    probes = read_lines(output / "probes.jsonl")
    expected_order = [(world, arm) for i, world in enumerate(WORLDS) for arm in ARMS[i:] + ARMS[:i]]
    check([(r["world_id"], r["arm"]) for r in episodes] == expected_order, "episode grid/order mismatch")
    check(len(traces) == 120 and len(probes) == 40, "wrong main/probe grid size")
    grouped_main, grouped_probe = defaultdict(list), defaultdict(list)
    for row in traces:
        grouped_main[row["episode_id"]].append(row)
    for row in probes:
        grouped_probe[row["episode_id"]].append(row)
    expected_ids = {f"{index:03d}-{arm}" for index, (_, arm) in enumerate(expected_order)}
    check(set(grouped_main) == set(grouped_probe) == expected_ids, "unknown or missing episode identity")
    ids, comparisons = set(), []
    authority_checks = 0
    for ordinal, episode in enumerate(episodes):
        identity = f"{ordinal:03d}-{episode['arm']}"
        world, arm = episode["world_id"], episode["arm"]
        check(episode["episode_id"] == identity and episode["method_version"] == METHOD and
              episode["counts_toward_verdict"] is False, "episode identity/verdict mismatch")
        check(episode["error"] is None and episode["outcome"] != "INVALID_ABORT", "aborted episode")
        main, branch = grouped_main[identity], grouped_probe[identity]
        check([r["step"] for r in main] == list(range(6)) and
              [r["step"] for r in branch] == [2, 4], "missing, duplicated or reordered step")
        branch_by_step = {r["step"]: r for r in branch}
        history, curve, local_comparisons = [], [], []
        for step, row in enumerate(main):
            check((row["world_id"], row["arm"]) == (world, arm), "trace world/arm mismatch")
            version, agent = source_version(world, step), agent_for(arm, step)
            check(row["agent"] == agent and row["task_version"] == version, "trace agent/version mismatch")
            initial = select_memory(arm, history, step, version)
            memory = check_context(row, world, step, initial, tokenizer, True)
            check(row["consumed_ids"] == [r["id"] for r in memory], "retained context IDs mismatch")
            authority_checks += check_call(row, memory, False, ids)
            check(row["record"] == record_for(row, agent), "main memory record mismatch")
            check_ledger(row["response"]["ledger"], main[:step + 1], 12288, 6)
            if step in (2, 4):
                probe = branch_by_step[step]
                check((probe["world_id"], probe["arm"]) == (world, arm), "probe world/arm mismatch")
                eligible = [r for r in memory if r["valid"] and r["agent"] != agent and r["task_version"] == version]
                removed = sorted(r["id"] for r in eligible)
                fork = [r for r in memory if r["id"] not in set(removed)]
                check(probe["removed_ids"] == removed and probe["eligible"] == bool(removed), "withheld intervention mismatch")
                check_context(probe, world, step, fork, tokenizer, False)
                authority_checks += check_call(probe, fork, True, ids)
                check(probe["request"]["seed"] == row["request"]["seed"], "paired seeds differ")
                check(probe["actual_semantic_action"] == row["result"]["semantic_action"] and
                      probe["actual_valid"] == row["result"]["valid"], "probe main-action reference mismatch")
                changed = row["result"]["semantic_action"] != probe["result"]["semantic_action"]
                check(probe["semantic_action_changed"] == changed, "probe action-change flag mismatch")
                check_ledger(probe["response"]["ledger"], branch[:(1 if step == 2 else 2)], 4096, 2)
                local_comparisons.append(classify_pair(row, probe, history))
                if not removed:
                    check(row["request"]["messages"] == probe["request"]["messages"], "no-eligible control changed prompt")
            history.append(row["record"])
            curve.append(dict(calls=step + 1, task_version=version, success=score(world, step, history),
                              tokens=sum(sum(usage([r]).values()) for r in main[:step + 1]),
                              elapsed_ns=sum(r["elapsed_ns"] for r in main[:step + 1])))
        comparisons.extend(local_comparisons)
        check(episode["curve"] == curve, "hidden prefix score/cost/latency curve mismatch")
        check(episode["outcome"] == ("success" if score(world, 5, history) else "failed"), "final selection/outcome mismatch")
        check(episode["main_calls"] == 6 and episode["probe_calls"] == 2 and episode["accounting_status"] == "KNOWN",
              "episode grid/accounting status mismatch")
        check(episode["main_usage"] == usage(main) and episode["probe_usage"] == usage(branch), "episode usage totals mismatch")
        for kind, rows, cap, count, suffix in (("main", main, 12288, 6, ""), ("probe", branch, 4096, 2, "-probe")):
            check_ledger(episode[kind + "_ledger"], rows, cap, count)
            check_database(output / (identity + suffix + ".sqlite"), episode[kind + "_ledger"])
        check(episode["eligible_probes"] == sum(p["eligible"] for p in local_comparisons), "eligible-probe aggregate mismatch")
        changes = sum(p["eligible"] and p["both_valid"] and p["semantic_action_changed"] for p in local_comparisons)
        check(episode["valid_action_changes"] == changes, "valid action-change aggregate mismatch")
        check_episode_accounting(episode, main, branch)
        check(episode["tool_receipt_bytes"] == sum(len(canonical(r["result"]).encode()) for r in main + branch),
              "tool receipt byte accounting mismatch")
        check(episode["peak_cuda_bytes"] == max(r["response"]["peak_cuda_bytes"] for r in main + branch), "peak GPU metric mismatch")
        check(episode["elapsed_ns"] >= sum(r["elapsed_ns"] for r in main + branch), "episode elapsed time excludes calls")

    summary = json.loads((output / "summary.json").read_text())
    check(summary["method_version"] == METHOD and summary["status"] == "PILOT_COMPLETE" and
          summary["counts_toward_verdict"] is False and set(summary["arms"]) == set(ARMS), "summary status/arms mismatch")
    for arm in ARMS:
        group = [r for r in episodes if r["arm"] == arm]
        expected = dict(episodes=4, successes=sum(r["outcome"] == "success" for r in group), invalid=0,
                        main_tokens=sum(sum(r["main_usage"].values()) for r in group),
                        probe_tokens=sum(sum(r["probe_usage"].values()) for r in group),
                        parser_admissions={kind: sum(r[kind + "_parser"]["admitted"] for r in group) for kind in ("main", "probe")},
                        public_valid_actions={kind: sum(r[kind + "_parser"]["public_valid_actions"] for r in group) for kind in ("main", "probe")},
                        processing_operations=sum(r["processing_operations"] for r in group),
                        processing_bytes=sum(r["processing_bytes"] for r in group),
                        transport_bytes=sum(r["transport_bytes"] for r in group),
                        serialized_trace_bytes=sum(r["serialized_trace_bytes"] for r in group),
                        eligible_probes=sum(r["eligible_probes"] for r in group),
                        valid_action_changes=sum(r["valid_action_changes"] for r in group),
                        curve=[dict(calls=k, observed=4, successes=sum(r["curve"][k - 1]["success"] for r in group),
                                    tokens=sum(r["curve"][k - 1]["tokens"] for r in group),
                                    elapsed_ns=sum(r["curve"][k - 1]["elapsed_ns"] for r in group)) for k in range(1, 7)])
        check(summary["arms"][arm] == expected, "per-arm summary/curve mismatch")
    check(pilot.summarize(episodes) == summary, "public summary does not reproduce")
    calls = traces + probes
    invalid = [r for r in calls if not r["result"]["valid"]]
    valid_changes = [p for p in comparisons if p["eligible"] and p["both_valid"] and p["semantic_action_changed"]]
    no_eligible = [p for p in comparisons if not p["eligible"]]
    result = dict(status="PASS_COMPLETE", method_version=METHOD, counts_toward_verdict=False,
                episodes=20, main_calls=120, probe_calls=40, installed_runtime_modules_checked=installed_count,
                frozen_files_checked=len(freeze["source_sha256"]), model_files_checked=len(manifest["sha256"]),
                authority_bindings_checked=authority_checks, verified_publications=sum(r["result"]["valid"] for r in calls),
                main_usage=usage(traces), probe_usage=usage(probes), total_tokens=sum(usage(calls).values()),
                offline_prompt_tokens=sum(r["response"]["prompt_tokens"] for r in calls),
                tokenizer_preflight_calls=sum(len(r["context_preflight"]) for r in calls),
                context_dropped_records=sum(len(r["context_dropped_ids"]) for r in calls),
                failed_actions=len(invalid), failed_action_tokens=sum(usage(invalid).values()),
                failure_feedback=dict(Counter(r["result"]["feedback"] for r in invalid)),
                main_successes=sum(r["outcome"] == "success" for r in episodes),
                main_action_counts=dict(Counter(r["result"]["action"] for r in traces)),
                eligible_probes=sum(p["eligible"] for p in comparisons), valid_action_changes=len(valid_changes),
                valid_change_families=sorted({p["world_id"].split("/", 1)[0] for p in valid_changes}),
                no_eligible_controls=len(no_eligible),
                no_eligible_exact_repeats=sum(p["same_output_text"] and p["same_completion_count"] for p in no_eligible),
                classifications=dict(Counter(p["classification"] for p in comparisons)),
                actual_prefix_only_successes=sum(p["actual_prefix_success"] and not p["withheld_prefix_success"] for p in comparisons),
                withheld_prefix_only_successes=sum(p["withheld_prefix_success"] and not p["actual_prefix_success"] for p in comparisons),
                comparisons=comparisons,
                completion_token_limitation="Raw generated token IDs were not retained. Completion counts reconcile with durable receipts and the frozen tensor-length implementation; decoded text cannot independently reconstruct every special token.",
                interpretation="Matched probes measure one-step effects of access to verified other-agent receipts and their workspace projection. A changed valid action is not necessarily better. Immediate prefix scoring is a post hoc diagnostic with identical previous submissions; no downstream branch was rolled out. Four previously observed worlds support no general efficacy claim.",
                checks=["complete grid and frozen sources", "installed runtime and model hashes", "offline prompt recount",
                        "public-only prompts", "independent history/context-drop reconstruction", "same-seed artifact withholding",
                        "public tool receipts", "generation/publication authority", "reservation and cumulative ledgers",
                        "40 durable SQLite ledgers", "hidden final selection and prefix curves", "summary and byte accounting",
                        "no-eligible repeatability and semantic-change classification"])

    result.update(additional_report(output, episodes, calls, freeze, context_path))
    return result


def results_markdown(result):
    lines = ["# R3 framed-action pilot v3 results", "",
        "**The pilot completed and its evidence reconciles. No useful semantic interaction gain was demonstrated; G5 remains incomplete.**", "",
        f"All 20 declared episodes, 120 main calls and 40 probes completed with known costs. "
        f"The common framing adapter admitted {result['parser_admissions']}/160 responses; "
        f"{sum(result['valid_actions_by_kind']['main'].values())} main and "
        f"{sum(result['valid_actions_by_kind']['probe'].values())} probe actions passed the unchanged public tool checker. "
        f"Final hidden evaluation succeeded in {result['main_successes']}/20 episodes.", "",
        "| Arm | Successes / 4 | Main tokens | Probe tokens | Eligible probes | Valid semantic changes |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for arm, values in result['by_arm'].items():
        lines.append(f"| {arm} | {values['successes']} | {values['main_tokens']:,} | {values['probe_tokens']:,} | {values['eligible_probes']} | {values['valid_action_changes']} |")
    lines += ["", f"Actual total usage is **{result['total_tokens']:,} tokens**, including "
        f"{result['failed_action_tokens']:,} tokens spent on {result['failed_actions']} rejected actions. "
        "All 40 final durable ledgers retain zero reserved or unknown tokens; rejected actions and failed tasks were retained.", "",
        f"There were {result['eligible_probes']} forks with eligible current verified artifacts from other agents, "
        f"and **{result['valid_action_changes']} semantic differences with both actions valid**. "
        f"Probe classifications: `{canonical(result['classifications'])}`. The {result['no_eligible_controls']} "
        f"no-eligible controls repeated text and completion count in {result['no_eligible_exact_repeats']} cases. "
        "Shared-artifact access was exercised, but these observations do not show useful behavioral adaptation "
        "or a coordination advantage. Probes are one-step forks; no alternative downstream rollout occurred.", "",
        f"Independent replay checked the complete grid, all original history/context selection and trimming, "
        f"raw-response normalization and receipt bindings, {result['authority_bindings_checked']} fresh public-core authority "
        f"projections, all tool/final/prefix evaluations, {result['offline_prompt_tokens']:,} prompt tokens with the frozen "
        f"offline tokenizer, all ledger rows and summary arithmetic. It verified {result['frozen_files_checked']} frozen "
        f"source/config/test files, {result['installed_artifacts_checked']} installed artifact hashes, "
        f"{result['bench_core_files_checked']} bench-core files and {result['model_files_checked']} model files. "
        "Raw generated token IDs were not stored, so completion-token counts are reconciled to durable receipts "
        "and the frozen tensor-length implementation rather than independently reconstructed from decoded text.", "",
        f"Logical accounting retained {result['costs']['processing_operations']:,} added processing operations, "
        f"{result['costs']['processing_bytes']:,} processing bytes, {result['costs']['transport_bytes']:,} raw transport bytes, "
        f"{result['costs']['serialized_trace_bytes']:,} serialized trace/probe bytes and "
        f"{result['costs']['tool_receipt_bytes']:,} tool-receipt bytes. These overlapping stage/storage measures "
        "are not independent physical I/O totals or money. Peak measured CUDA tensor allocation was "
        f"{result['peak_cuda_bytes']:,} bytes, excluding other device/process memory.", "",
        "The model remains Qwen/Qwen2.5-Coder-1.5B-Instruct revision "
        "`2e1fd397ee46e1388853d2af2c993145b0f1098a`, float16, on RTX 5070 Laptop "
        "with PyTorch 2.11.0+cu128, Transformers 4.57.3 and Python 3.12.3. "
        "One resident model served logical agents sequentially. CPU wheel/sdist acceptance ran concurrently "
        "from 2026-09-13 03:41:20.818771 UTC through 03:43:02.243118 UTC, using separate installation targets "
        "and leaving the GPU environment unchanged. The final main trace was written at "
        f"{result['evidence_file_mtime_utc']['trace.jsonl']}. These file timestamps and the attached acceptance "
        "receipt document overlap; they are not an isolated timing instrument. Wall and GPU elapsed numbers "
        "must remain descriptive, not a fair latency, throughput or scaling ranking.", "",
        "This is a separately frozen engineering pilot selected after the v2 format diagnostic, using "
        "four previously observed worlds and seed 1073. The earlier failed runs remain unchanged. "
        "No held-out or confirmatory evidence, noninferiority test, general model capability claim, "
        "R4 scaling result or strategy promotion follows. New tasks, models, parsers or escalation "
        "require a separately declared experiment. Runtime development-authority and recovery limitations remain.", "",
        "Evidence: [frozen inputs](freeze.json), [environment](environment.json), [episodes](episodes.jsonl), "
        "[raw main trace](trace.jsonl), [probes](probes.jsonl), [summary](summary.json), "
        "[independent audit](independent_audit.json), [audit artifact hashes](independent-audit-hashes.json). "
        "The independent audit embeds the CPU acceptance context and source/evidence hashes. "
        "It made no new generation calls and did not modify frozen evidence."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model-path', type=Path, required=True)
    parser.add_argument('--acceptance-context', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    for name in ('independent_audit.json', 'RESULTS.md', 'independent-audit-hashes.json'):
        check(not (output / name).exists(), 'refusing to overwrite audit report: ' + name)
    input_hashes = {path.name: file_hash(path) for path in sorted(output.iterdir()) if path.is_file()}
    result = audit(output, args.model_path.resolve(), args.acceptance_context.resolve())
    check(all(file_hash(output / name) == expected for name, expected in input_hashes.items()), 'input evidence changed during audit')
    result['source_evidence_sha256'] = input_hashes
    result['audit_source_sha256'] = {str(path.resolve()): file_hash(path) for path in (Path(__file__), Path(previous.__file__))}
    with (output / 'independent_audit.json').open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    with (output / 'RESULTS.md').open('x') as stream:
        stream.write(results_markdown(result))
    with (output / 'independent-audit-hashes.json').open('x') as stream:
        stream.write(json.dumps({name: file_hash(output / name) for name in ('independent_audit.json', 'RESULTS.md')}, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'main_successes', 'total_tokens', 'verified_publications',
          'eligible_probes', 'valid_action_changes', 'failed_actions', 'failed_action_tokens', 'classifications')}, indent=2))


if __name__ == '__main__':
    main()
