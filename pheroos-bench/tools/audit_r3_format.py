"""Posthoc offline R3 format diagnosis; preserves all original pilot outcomes.

Only a sole lower-case ``json`` Markdown fence containing one strict JSON object
is unwrapped. The unchanged public task checker receives the original history;
normalized artifacts never enter another call's history. No model, authority,
hidden final scorer, or generated host code is executed.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from pheroos_bench import r3_tasks, r3_tool_tasks as tasks

METHOD = "r3_format_posthoc_audit_v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(value).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def strict_object(text):
    value = json.loads(text, object_pairs_hook=r3_tasks._object,
                       parse_constant=r3_tasks._nonfinite)
    if type(value) is not dict:
        raise ValueError("JSON value is not an object")
    return value


def classify(text):
    """Return a classification and eligible body without editing its contents."""
    check(type(text) is str, "response text is not a string")
    match = re.fullmatch(r"```([A-Za-z0-9_-]*)[ \t]*\r?\n([\s\S]*?)\r?\n```", text.strip())
    if match and not re.search(r"(?m)^[ \t]*```", match[2]):
        language, body = match.groups()
        if language != "json":
            return {"class": "sole_python_fence" if language in ("python", "py")
                    else "sole_other_fence", "language": language, "body": None}
        try:
            strict_object(body)
        except (ValueError, TypeError, RecursionError) as error:
            return {"class": "sole_json_fence_invalid_object", "language": language,
                    "body": None, "reason": str(error)}
        return {"class": "sole_json_fence_object", "language": language, "body": body}
    if "```" in text:
        return {"class": "fence_with_prose_or_multiple_blocks", "body": None}
    try:
        strict_object(text)
        return {"class": "bare_json_object", "body": None}
    except (ValueError, TypeError, RecursionError):
        return {"class": "other_prose_or_invalid_json", "body": None}


def evaluate_call(row, memory):
    """Check original receipt, then independently test the one allowed unwrap."""
    text = row["response"]["text"]
    check(row["request"]["messages"] == tasks.messages_for(row["world_id"], row["step"], memory),
          "request does not match original public history")
    original = tasks.apply(row["world_id"], row["step"], memory, text)
    check(original == row["result"], "original action receipt does not reproduce")
    classification = classify(text)
    body = classification.pop("body")
    normalized = tasks.apply(row["world_id"], row["step"], memory, body) if body is not None else None
    return {"classification": classification, "original_result": original,
            "normalization_attempted": body is not None,
            "normalized_body_sha256": digest(body.encode()) if body is not None else None,
            "posthoc_result": normalized}


def read_rows(path):
    return [(json.loads(line), digest(line)) for line in path.read_bytes().splitlines()
            if line.strip()]


def audit(source: Path, runtime_source: Path):
    source = source.resolve()
    freeze = json.loads((source / "freeze.json").read_text())
    config = freeze["config"]
    check(config["method_version"] == "r3_tool_loop_pilot_v2", "wrong source method")
    check(freeze["frozen_before_calls"] is True, "source lacks pre-call freeze")
    check(not (source / "abort.json").exists(), "source contains INVALID_ABORT")
    frozen = []
    for original_path, expected in freeze["source_sha256"].items():
        path = Path(original_path)
        for old in ("/tmp/PheroOS-runtime", "/home/scott/projects/PheroOS-runtime"):
            if str(path).startswith(old + "/"):
                path = runtime_source / path.relative_to(old)
                break
        actual = digest(path.read_bytes())
        check(actual == expected, f"frozen source mismatch: {path}")
        frozen.append({"original_path": original_path, "resolved_path": str(path.resolve()),
                       "sha256": actual})
    for module in (tasks, r3_tasks):
        path = Path(module.__file__).resolve()
        check(any(item["resolved_path"] == str(path) for item in frozen), "unfrozen task import")
    original_files = {path.name: {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
                      for path in sorted(source.iterdir()) if path.is_file()}
    episodes = [row for row, _ in read_rows(source / "episodes.jsonl")]
    episode_map = {row["episode_id"]: row for row in episodes}
    check(len(episodes) == len(episode_map), "duplicate source episode")
    check({(r["world_id"], r["arm"]) for r in episodes}
          == {(world, arm) for world in config["worlds"] for arm in config["arms"]}
          and len(episodes) == len(config["worlds"]) * len(config["arms"]), "incomplete episode grid")
    traces = read_rows(source / "trace.jsonl")
    probes = read_rows(source / "probes.jsonl")
    main = {(r["episode_id"], r["step"]): r for r, _ in traces}
    check(len(main) == len(traces), "duplicate main call")
    check(set(main) == {(ep, step) for ep in episode_map for step in range(config["steps"])},
          "incomplete main call grid")
    check(len(probes) == len(episode_map) * len(config["probe_steps"])
          and {(r["episode_id"], r["step"]) for r, _ in probes}
          == {(ep, step) for ep in episode_map for step in config["probe_steps"]}, "incomplete probe grid")
    records = {r["record"]["id"]: r["record"] for r, _ in traces}
    calls = []
    for kind, rows in (("main", traces), ("probe", probes)):
        for row, line_hash in rows:
            episode = episode_map[row["episode_id"]]
            check(episode["counts_toward_verdict"] is False and episode["accounting_status"] == "KNOWN",
                  "nonpilot or unknown source accounting")
            check(row["status"] == "received", "incomplete source call")
            original_main = main[(row["episode_id"], row["step"])]
            removed = row["removed_ids"] if kind == "probe" else []
            ids = [identity for identity in original_main["consumed_ids"] if identity not in removed]
            check(set(removed) <= set(original_main["consumed_ids"]), "probe removes undeclared memory")
            memory = [records[identity] for identity in ids]
            check(all(record["step"] < row["step"] and
                      identity.startswith(row["episode_id"] + ":artifact:")
                      for identity, record in zip(ids, memory)), "noncausal or foreign history")
            result = evaluate_call(row, memory)
            response = row["response"]
            check(all(type(response[k]) is int and response[k] >= 0
                      for k in ("prompt_tokens", "completion_tokens")), "invalid usage")
            calls.append({"method_version": METHOD, "counts_toward_verdict": False,
                          "phase": "posthoc_diagnostic", "kind": kind,
                          "episode_id": row["episode_id"], "world_id": row["world_id"],
                          "arm": row["arm"], "step": row["step"], "call_id": row["request"]["call_id"],
                          "original_status": row["status"], "original_episode_outcome": episode["outcome"],
                          "original_memory_ids": ids, "original_row_sha256": line_hash,
                          "original_request_sha256": digest(canonical(row["request"]).encode()),
                          "original_response_sha256": digest(canonical(response).encode()),
                          "original_text_sha256": digest(response["text"].encode()),
                          "prompt_tokens": response["prompt_tokens"],
                          "completion_tokens": response["completion_tokens"],
                          **result})
    for episode in episodes:
        for kind in ("main", "probe"):
            selected = [row for row in calls if row["episode_id"] == episode["episode_id"] and row["kind"] == kind]
            ledger = episode[kind + "_ledger"]
            check(ledger["unknown_tokens"] == ledger["reserved_tokens"] == 0, "unresolved ledger")
            check(len(selected) == episode[kind + "_calls"] == ledger["call_count"], "call count mismatch")
            usage = {"input_tokens": sum(r["prompt_tokens"] for r in selected),
                     "output_tokens": sum(r["completion_tokens"] for r in selected)}
            check(usage == episode[kind + "_usage"] and sum(usage.values()) == ledger["actual_tokens"],
                  "reported token accounting mismatch")
    summary = {"method_version": METHOD, "status": "POSTHOC_DIAGNOSTIC_COMPLETE",
               "phase": "posthoc_diagnostic", "counts_toward_verdict": False,
               "source_method": config["method_version"], "source_task_version": tasks.DATA_VERSION,
               "source_verifier_version": r3_tasks.DATA_VERSION,
               "original_episode_outcomes": dict(Counter(r["outcome"] for r in episodes)),
               "original_calls": len(calls),
               "original_valid_actions": sum(r["original_result"]["valid"] for r in calls),
               "classifications": dict(Counter(r["classification"]["class"] for r in calls)),
               "normalization_rule": "unwrap only sole lower-case json fence with one strict JSON object; no content edits",
               "history_rule": "each call uses its original history; no normalized artifacts propagated; no final rescoring",
               "posthoc_admitted_actions": sum(bool(r["posthoc_result"] and r["posthoc_result"]["valid"]) for r in calls),
               "by_kind": {}, "limitations": [
                   "posthoc analysis of observed responses, not a new rollout or efficacy evidence",
                   "public-valid actions are not hidden-test success, governed publication, or useful collaboration",
                   "normalization was selected after seeing format failures; future tests need a separate pre-call freeze",
                   "original token costs and failed episode outcomes remain unchanged; no additional model calls",
                   "one checkpoint and four previously observed worlds do not establish a general model capability floor"]}
    for kind in ("main", "probe"):
        selected = [row for row in calls if row["kind"] == kind]
        admitted = [r for r in selected if r["posthoc_result"] and r["posthoc_result"]["valid"]]
        summary["by_kind"][kind] = {
            "calls": len(selected), "input_tokens": sum(r["prompt_tokens"] for r in selected),
            "output_tokens": sum(r["completion_tokens"] for r in selected), "unknown_tokens": 0,
            "posthoc_admitted_by_action": dict(Counter(r["posthoc_result"]["action"] for r in admitted)),
            "posthoc_feedback": dict(Counter(r["posthoc_result"]["feedback"] for r in selected if r["posthoc_result"]))}
    check(all(digest((source / name).read_bytes()) == item["sha256"]
              for name, item in original_files.items()), "source evidence changed during audit")
    manifest = {"method_version": METHOD, "counts_toward_verdict": False,
                "source_directory": str(source), "source_files": original_files,
                "frozen_sources_verified": frozen,
                "audit_sources": {str(path.resolve()): digest(path.read_bytes()) for path in
                                  [Path(__file__), Path(__file__).parents[1] / "tests/test_r3_format_audit.py"]}}
    return summary, calls, manifest


def report(summary):
    main, probe = (summary["by_kind"][kind] for kind in ("main", "probe"))
    return (
        "# R3 format diagnostic v1\n\n"
        f"Original outcomes remain **{summary['original_episode_outcomes']}**, with "
        f"**{summary['original_valid_actions']}/{summary['original_calls']} valid actions**. "
        "Every original call and its cost is retained in `calls.jsonl`; historical evidence is untouched.\n\n"
        f"Format classifications: `{canonical(summary['classifications'])}`. Unwrapping only a sole "
        "lower-case JSON fence, without editing its contents, yields "
        f"**{summary['posthoc_admitted_actions']} posthoc public-valid actions** against their original histories. "
        f"Main admissions: `{canonical(main['posthoc_admitted_by_action'])}`; probe admissions: "
        f"`{canonical(probe['posthoc_admitted_by_action'])}`. These are potential parser admissions, "
        "not observed successful rollouts, authorized publications, or collaboration gains.\n\n"
        f"Actual original usage remains **{main['input_tokens'] + main['output_tokens']:,} main tokens + "
        f"{probe['input_tokens'] + probe['output_tokens']:,} probe tokens**; unknown tokens are zero. "
        "This offline audit made no model calls and did not run the hidden final scorer.\n\n"
        "A separately frozen capability-admission pilot is justified to distinguish the exact action-format "
        "failure from other capability limits. It must declare any normalization rule, prompts, "
        "tasks, evaluator, limits, and stopping decision before calls; give every policy the same interface; "
        "and preserve failures and costs. This audit does not pass G5, justify an R4 efficacy comparison, "
        "or promote a policy. No original history was rewritten and no normalized artifact was propagated.\n\n"
        "`manifest.json` binds every source evidence file, the verified historical source freeze, "
        "and this audit's source/tests. `summary.json` and `calls.jsonl` are explicitly posthoc diagnostics "
        "with `counts_toward_verdict=false`.\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--runtime-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    check(not args.output.exists(), "refusing to overwrite output")
    summary, calls, manifest = audit(args.source, args.runtime_source.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in (("summary.json", summary), ("manifest.json", manifest)):
        (args.output / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    (args.output / "calls.jsonl").write_text("".join(canonical(row) + "\n" for row in calls))
    (args.output / "GATE-REPORT.md").write_text(report(summary))
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
