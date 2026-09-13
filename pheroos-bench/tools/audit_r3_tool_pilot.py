"""Independently reconcile a completed R3 v2 pilot; never generates a model call.

Run with the installed runtime interpreter and bench ``src`` on PYTHONPATH.
``--path-map OLD=NEW`` relocates frozen source paths without changing evidence.
Reports are new files; existing reports and experimental evidence are untouched.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from pheroos.kernel import RuntimeScope
from pheroos_bench import r3_tasks, r3_tool_tasks as tasks
import pheroos_runtime
from pheroos_runtime.authority import authorize_r3


ARMS = ("single", "independent", "manager_graph", "blackboard", "versioned_blackboard")
METHOD = "r3_tool_loop_pilot_v2"
WORLDS = ("code_repair/clamp", "code_repair/chunk_count",
          "evidence_revision/dispatch_limit", "evidence_revision/channel_route")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def file_hash(path):
    value = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def source_version(world, step):
    return 1 if world.startswith("code_repair/") or step < 3 else 2


def agent_for(arm, step):
    index = 0 if arm == "single" else step // 3 if arm == "independent" else (
        step // 2 if arm == "manager_graph" else step)
    return f"agent{index}"


def select_memory(arm, history, step, version):
    previous = [r for r in history if r["step"] < step]
    if arm == "single":
        return previous[-6:]
    if arm == "independent":
        return [r for r in previous if r["agent"] == agent_for(arm, step)]
    if arm == "manager_graph":
        return previous[-2:]
    if arm == "blackboard":
        return previous[-3:]
    selected, seen = [], set()
    for record in reversed(previous):
        if record["task_version"] == version and record["receipt_digest"] not in seen:
            selected.append(record)
            seen.add(record["receipt_digest"])
            if len(selected) == 3:
                break
    return list(reversed(selected))


def score(world, step, history):
    current = source_version(world, step)
    eligible = [r for r in history if r["valid"] and r["task_version"] == current
                and r["artifact"]["world_id"] == world
                and r["artifact"]["task_version"] == current
                and r["artifact"]["kind"] == "submitted_candidate"]
    if not eligible:
        return False
    candidate = eligible[-1]["artifact"]["receipt"]["candidate"]
    normalized = {"code": "\n".join(candidate["code_lines"])} if "code_lines" in candidate else candidate
    return r3_tasks.verify(world, 0 if step < 3 else 2, canonical(normalized), final=True)["valid"]


def record_for(row, agent):
    result = row["result"]
    return dict(id=f"{row['episode_id']}:artifact:{row['step']}", agent=agent,
                step=row["step"], task_version=source_version(row["world_id"], row["step"]),
                **{key: result[key] for key in
                   ("valid", "feedback", "artifact", "action", "semantic_action")},
                receipt_digest=sha256(canonical(result["artifact"]).encode()).hexdigest())


def public_prompt_check(messages, world, step, memory):
    check(messages == tasks.messages_for(world, step, memory), "prompt differs from declared public construction")
    content = json.loads(messages[1]["content"])
    check(set(content) == {"task", "tool_receipts"}, "unexpected prompt field")
    public = content["task"]
    common = {"data_version", "world_id", "task_version", "turn", "total_turns", "instruction", "submit_example"}
    specific = ({"original_source", "workspace_code_lines", "test_index", "supported_python"}
                if world.startswith("code_repair/") else
                {"source_index", "source_update_turn", "citations_rule"})
    check(set(public) == common | specific, "task exposes an undeclared field")
    check(public["world_id"] == world and public["task_version"] == source_version(world, step),
          "public task identity/version mismatch")
    check(public["turn"] == step + 1 and public["total_turns"] == 6, "public turn mismatch")
    receipts = [{k: r[k] for k in ("id", "agent", "step", "task_version", "valid", "feedback", "artifact")}
                for r in memory]
    check(content["tool_receipts"] == receipts, "prompt contains hidden feedback or foreign receipts")


def check_context(row, world, step, initial, tokenizer, allow_trim):
    memory = list(initial)
    preflights = row["context_preflight"]
    dropped = row["context_dropped_ids"]
    check(len(preflights) == len(dropped) + 1, "missing context preflight/drop")
    check(allow_trim or not dropped, "probe silently trimmed additional records")
    for index, preflight in enumerate(preflights):
        check(set(preflight) == {"request", "response"}, "unexpected preflight fields")
        messages = preflight["request"]["messages"]
        check(preflight["request"]["op"] == "tokenize", "preflight is not tokenize")
        public_prompt_check(messages, world, step, memory)
        count = len(tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=True))
        check(preflight["response"] == {"prompt_tokens": count}, "offline tokenizer preflight count mismatch")
        if index < len(dropped):
            check(count + 256 > 2048 and memory, "unnecessary or impossible context drop")
            check(memory.pop(0)["id"] == dropped[index], "context trim did not drop oldest whole receipt")
        else:
            check(count + 256 <= 2048, "fitted context exceeds cap")
            check(row["request"]["messages"] == messages, "generated prompt differs from fitted prompt")
            check(row["response"]["prompt_tokens"] == count, "generated prompt token usage differs")
    return memory


def check_ledger(snapshot, rows, cap, max_calls):
    expected_calls = []
    cumulative = 0
    for row in rows:
        request, response = row["request"], row["response"]
        payload = {k: request[k] for k in ("task_id", "version", "call_id", "messages", "max_new_tokens", "seed")}
        usage = response["prompt_tokens"] + response["completion_tokens"]
        reserved = response["prompt_tokens"] + request["max_new_tokens"]
        check(cumulative + reserved <= cap, "reservation exceeds episode budget")
        cumulative += usage
        expected_calls.append(dict(id=request["call_id"], state="received", request=payload,
                                   response={k: v for k, v in response.items() if k not in ("authority", "ledger")},
                                   reserved=reserved, actual=usage))
    expected = dict(config={"token_cap": cap, "max_calls": max_calls}, calls=expected_calls,
                    actual_tokens=cumulative, reserved_tokens=0, unknown_tokens=0, call_count=len(rows))
    check(snapshot == expected, "cumulative ledger differs from requests/receipts")


def check_database(path, ledger):
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        config = connection.execute("SELECT value FROM config").fetchall()
        check(len(config) == 1 and json.loads(config[0][0]) == ledger["config"], "SQLite config mismatch")
        rows = connection.execute("SELECT * FROM calls ORDER BY rowid").fetchall()
    finally:
        connection.close()
    check(len(rows) == len(ledger["calls"]), "SQLite call count mismatch")
    for actual, reported in zip(rows, ledger["calls"]):
        check({k: actual[k] for k in ("id", "state", "reserved", "actual")} ==
              {k: reported[k] for k in ("id", "state", "reserved", "actual")}, "SQLite amounts/state mismatch")
        check(json.loads(actual["request"]) == reported["request"] and
              json.loads(actual["response"]) == reported["response"], "SQLite request/receipt mismatch")
        check(actual["prompt_tokens"] == reported["response"]["prompt_tokens"] and
              actual["max_new_tokens"] == 256, "SQLite reservation inputs mismatch")


def check_call(row, memory, is_probe, checked_ids):
    world, step = row["world_id"], row["step"]
    request, response = row["request"], row["response"]
    check(row["status"] == "received" and response is not None, "unacknowledged/aborted model call")
    check(request["call_id"] not in checked_ids, "duplicate model call ID")
    checked_ids.add(request["call_id"])
    suffix = "-probe" if is_probe else ""
    check(request["scope"] == RuntimeScope("r3-tool-pilot-v2", row["episode_id"] + suffix, "episode").to_dict(),
          "wrong main/probe scope")
    check(request["op"] == "generate" and request["task_id"] == world and
          request["version"] == source_version(world, step), "generation target/version mismatch")
    expected_id = f"{row['episode_id']}:{'probe:' if is_probe else ''}{step}"
    check(request["call_id"] == expected_id, "generation call ID mismatch")
    check(Path(request["ledger_path"]).name == row["episode_id"] + suffix + ".sqlite", "wrong ledger path")
    check(request["max_calls"] == (2 if is_probe else 6) and
          request["token_cap"] == (4096 if is_probe else 12288), "wrong branch budget")
    check(request["seed"] == 71 + WORLDS.index(world) * 100 + step, "wrong paired generation seed")
    check(request["max_new_tokens"] == 256, "wrong output cap")
    check(all(type(response[k]) is int and response[k] >= 0 for k in
              ("prompt_tokens", "completion_tokens", "elapsed_ns", "peak_cuda_bytes")), "invalid generation metrics")
    check(0 < response["prompt_tokens"] and response["completion_tokens"] <= 256 and
          response["prompt_tokens"] + 256 <= 2048, "generation context/output bound violated")
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


def usage(rows):
    return {key: sum(r["response"][field] for r in rows)
            for key, field in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"))}


def bytes_for(rows):
    return sum(sum(len(canonical(r[k]).encode()) for k in
                   ("request", "response", "publication_request", "publication") if r[k] is not None)
               + sum(len(canonical(p[k]).encode()) for p in r["context_preflight"]
                     for k in ("request", "response")) for r in rows)


def classify_pair(actual, probe, history):
    eligible = probe["eligible"]
    left, right = actual["result"], probe["result"]
    changed = left["semantic_action"] != right["semantic_action"]
    both_valid = left["valid"] and right["valid"]
    if not eligible:
        classification = "no_eligible_exact_repeat" if actual["response"]["text"] == probe["response"]["text"] else "no_eligible_nonrepeat"
    elif not both_valid:
        classification = "invalid_action_in_pair"
    elif not changed:
        classification = "same_declared_semantic_action"
    elif left["action"] != right["action"]:
        classification = "actual_" + left["action"] + "_withheld_" + right["action"]
    elif left["action"] == "inspect":
        classification = "different_inspection_target"
    elif actual["world_id"].startswith("code_repair/"):
        classification = "different_code_on_declared_finite_probes"
    else:
        classification = "different_evidence_answer_or_citations"
    alternative = record_for(probe, agent_for(actual["arm"], actual["step"]))
    # The fork changes access to history, not the existence of previously submitted
    # candidates. Both immediate selectors therefore start from identical history.
    return dict(call_id=actual["request"]["call_id"], world_id=actual["world_id"], arm=actual["arm"],
                eligible=eligible, removed_ids=probe["removed_ids"], classification=classification,
                both_valid=both_valid, semantic_action_changed=changed,
                same_prompt=actual["request"]["messages"] == probe["request"]["messages"],
                same_output_text=actual["response"]["text"] == probe["response"]["text"],
                same_completion_count=actual["response"]["completion_tokens"] == probe["response"]["completion_tokens"],
                actual_action=left["semantic_action"], withheld_action=right["semantic_action"],
                actual_prefix_success=score(actual["world_id"], actual["step"], history + [actual["record"]]),
                withheld_prefix_success=score(actual["world_id"], actual["step"], history + [alternative]))


def audit(output, model_path, path_maps):
    check((output / "summary.json").is_file(), "pilot is incomplete; refusing partial/final audit")
    check(not (output / "abort.json").exists(), "pilot contains abort evidence")
    freeze = json.loads((output / "freeze.json").read_text())
    config = dict(method_version=METHOD, arms=list(ARMS), worlds=list(WORLDS), steps=6,
                  max_new_tokens=256, episode_token_cap=12288, probe_steps=[2, 4], probe_token_cap=4096, seed=71)
    check(freeze["config"] == config and freeze["frozen_before_calls"] is True, "wrong pre-run freeze/config")
    required_sources = {
        "r3_tool_pilot.py", "r3_tool_tasks.py", "r3_pilot.py", "r3_tasks.py",
        "r3-tool-pilot-v2.json", "R3-tool-loop-v2-contract.md",
        "test_r3_tool_pilot.py", "test_r3_tool_tasks.py",
        "__init__.py", "adapters.py", "authority.py", "cli.py", "engine.py",
        "r3_ledger.py", "r3_local.py", "store.py",
    }
    check(len(freeze["source_sha256"]) == len(required_sources) and
          {Path(name).name for name in freeze["source_sha256"]} == required_sources,
          "missing or unexpected frozen source/test/contract file")

    def relocate(name):
        for before, after in path_maps:
            if name == before or name.startswith(before.rstrip("/") + "/"):
                return Path(after + name[len(before):])
        return Path(name)

    installed = Path(pheroos_runtime.__file__).resolve().parent
    installed_count = 0
    for name, digest in freeze["source_sha256"].items():
        source = relocate(name)
        check(file_hash(source) == digest, "frozen source mismatch: " + name)
        if "/src/pheroos_runtime/" in name:
            check(file_hash(installed / source.name) == digest, "installed runtime differs from freeze: " + name)
            installed_count += 1
    for module in (tasks, r3_tasks):
        matches = [digest for name, digest in freeze["source_sha256"].items() if name.endswith("/" + Path(module.__file__).name)]
        check(matches == [file_hash(Path(module.__file__))], "audit imported a non-frozen task module")
    manifest = json.loads((model_path / "manifest.json").read_text())
    check(manifest == freeze["model"], "model manifest differs from freeze")
    for name, digest in manifest["sha256"].items():
        check(file_hash(model_path / name) == digest, "model file differs from manifest: " + name)
    environment = json.loads((output / "environment.json").read_text())
    check(environment["model_manifest"] == manifest, "loaded model manifest mismatch")
    # Deliberately deferred until completion; this audit does not compete with GPU runs.
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)

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
        check(episode["transport_bytes"] == bytes_for(main + branch), "transport/tokenizer byte accounting mismatch")
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
                        eligible_probes=sum(r["eligible_probes"] for r in group),
                        valid_action_changes=sum(r["valid_action_changes"] for r in group),
                        curve=[dict(calls=k, observed=4, successes=sum(r["curve"][k - 1]["success"] for r in group),
                                    tokens=sum(r["curve"][k - 1]["tokens"] for r in group),
                                    elapsed_ns=sum(r["curve"][k - 1]["elapsed_ns"] for r in group)) for k in range(1, 7)])
        check(summary["arms"][arm] == expected, "per-arm summary/curve mismatch")
    calls = traces + probes
    invalid = [r for r in calls if not r["result"]["valid"]]
    valid_changes = [p for p in comparisons if p["eligible"] and p["both_valid"] and p["semantic_action_changed"]]
    no_eligible = [p for p in comparisons if not p["eligible"]]
    return dict(status="PASS_COMPLETE", method_version=METHOD, counts_toward_verdict=False,
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


def report_markdown(result):
    return "\n".join([
        "# Independent R3 v2 audit", "", f"Evidence consistency: **{result['status']}**. This is an engineering audit, not an efficacy verdict.", "",
        f"Reconciled {result['episodes']} episodes, {result['main_calls']} main calls and {result['probe_calls']} probes. "
        f"Total usage is **{result['total_tokens']:,} tokens**; main {sum(result['main_usage'].values()):,}, probes {sum(result['probe_usage'].values()):,}. "
        f"All 40 final SQLite ledgers retain zero reserved or unknown tokens. {result['failed_actions']} rejected actions consumed "
        f"{result['failed_action_tokens']:,} tokens, included in those totals.", "",
        f"Checked {result['authority_bindings_checked']} authority bindings, {result['verified_publications']} publications, "
        f"{result['frozen_files_checked']} frozen files, {result['installed_runtime_modules_checked']} installed runtime modules and "
        f"{result['model_files_checked']} model files. The offline tokenizer reproduced all {result['offline_prompt_tokens']:,} "
        f"generation input tokens and every preflight count. {result['context_dropped_records']} whole records were dropped by the frozen context rule.", "",
        f"There are {result['eligible_probes']} eligible forks and {result['valid_action_changes']} differences with both actions valid. "
        f"Families with such differences: {', '.join(result['valid_change_families']) or 'none'}. "
        f"No-eligible controls repeat output text and completion count in {result['no_eligible_exact_repeats']}/{result['no_eligible_controls']} cases.", "",
        f"Final main-episode successes: {result['main_successes']}/20. In the post hoc immediate-prefix diagnostic, "
        f"the actual branch succeeds alone in {result['actual_prefix_only_successes']} forks, and the withheld branch succeeds alone "
        f"in {result['withheld_prefix_only_successes']} forks. Previous submissions remain identical; these are not downstream rollouts.", "",
        result["interpretation"], "", result["completion_token_limitation"], "",
        "Elapsed times include runtime authorization and tokenizer work; probe interleaving prevents interpreting them as pure GPU throughput. "
        "Workspace is a projection of retained receipts, not a persistent shared repository.", "",
        "The JSON report retains every fork's classification, actions and immediate prefix checks. No frozen experiment files or outcomes were changed.", "",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="completed pilot evidence directory")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--path-map", action="append", default=[], metavar="OLD=NEW")
    parser.add_argument("--write-reports", action="store_true", help="create independent_audit.json and INDEPENDENT-AUDIT.md exclusively")
    args = parser.parse_args()
    mappings = []
    for mapping in args.path_map:
        before, after = mapping.split("=", 1)
        mappings.append((before.rstrip("/"), after.rstrip("/")))
    result = audit(args.output, args.model_path, mappings)
    if args.write_reports:
        paths = (args.output / "independent_audit.json", args.output / "INDEPENDENT-AUDIT.md")
        check(not any(p.exists() for p in paths), "refusing to overwrite an existing audit report")
        with paths[0].open("x") as stream:
            stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
        with paths[1].open("x") as stream:
            stream.write(report_markdown(result))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
