"""Versioned, finite tool actions over the unchanged R3 v1 task fixtures.

Tools return actual bounded-interpreter or closed-document receipts. A patch
changes only the workspace reconstructed from the caller's visible receipts.
The final scorer is never consulted when constructing model feedback.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from hashlib import sha256
import json

from . import r3_tasks


DATA_VERSION = "r3_tool_task_fixtures_v2"
ARMS = ("single", "independent", "manager_graph", "blackboard", "versioned_blackboard")
STEPS = 6
# These fixed, disclosed contract inputs are independent of the final scorer.
# They describe action semantics, not correctness or complete program equality.
PUBLIC_PROBES = {
    "code_repair/clamp": ((-1, -1, 1), (0, -1, 1), (1, -1, 1), (2, -1, 1)),
    "code_repair/chunk_count": ((2, 2), (4, 3), (2, 5), (6, 2)),
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _step(step):
    if type(step) is not int or not 0 <= step < STEPS:
        raise ValueError("step must be an integer from zero through five")


def _v1_step(step):
    _step(step)
    return 0 if step < 3 else 2


def world_ids():
    return r3_tasks.world_ids()


def version(world, step):
    """Evidence sources update at step three in every arm."""
    return r3_tasks.public_view(world, _v1_step(step))["task_version"]


def agent_for(arm, step):
    _step(step)
    if arm not in ARMS:
        raise ValueError("undeclared arm")
    index = 0 if arm == "single" else step // 3 if arm == "independent" else (
        step // 2 if arm == "manager_graph" else step
    )
    return f"agent{index}"


def memory_for(arm, records, step, task_version):
    """Select past receipts using only the arm's declared visibility policy."""
    agent = agent_for(arm, step)
    previous = [record for record in records if record["step"] < step]
    if arm == "single":
        selected = previous[-6:]
    elif arm == "independent":
        selected = [record for record in previous if record["agent"] == agent]
    elif arm == "manager_graph":
        selected = previous[-2:]
    elif arm == "blackboard":
        selected = previous[-3:]
    else:
        selected, seen = [], set()
        for record in reversed(previous):
            if record["task_version"] != task_version or record["receipt_digest"] in seen:
                continue
            seen.add(record["receipt_digest"])
            selected.append(record)
            if len(selected) == 3:
                break
        selected.reverse()
    return deepcopy(selected)


def _eligible(world, step, records, kind):
    current = version(world, step)
    for record in records:
        artifact = record.get("artifact")
        if (
            record.get("valid") is True
            and type(record.get("step")) is int
            and 0 <= record["step"] <= step
            and record.get("task_version") == current
            and type(artifact) is dict
            and artifact.get("world_id") == world
            and artifact.get("task_version") == current
            and artifact.get("kind") == kind
        ):
            yield record


def _code(candidate):
    if type(candidate) is not dict or set(candidate) != {"code_lines"}:
        raise ValueError("code candidate requires exactly code_lines")
    lines = candidate["code_lines"]
    if type(lines) is not list or not lines or any(type(line) is not str for line in lines):
        raise ValueError("code_lines must be a nonempty list of strings")
    if any("\n" in line or "\r" in line for line in lines):
        raise ValueError("each code_lines item must contain exactly one source line")
    return "\n".join(lines)


def _workspace(world, step, memory):
    source = r3_tasks.public_view(world, _v1_step(step))["source"]
    for record in _eligible(world, step, memory, "submitted_candidate"):
        if record["step"] < step:
            source = _code(record["artifact"]["receipt"]["candidate"])
    return source


def _function(world, source):
    original = r3_tasks.public_view(world, 0)["source"]
    definition = ast.parse(original).body[0]
    return r3_tasks._IntegerFunction(
        source, definition.name, [argument.arg for argument in definition.args.args]
    )


def _public_task(world, step, memory):
    view = r3_tasks.public_view(world, _v1_step(step))
    task = {
        "data_version": DATA_VERSION, "world_id": world,
        "task_version": view["task_version"], "turn": step + 1, "total_turns": STEPS,
    }
    if view["family"] == "code_repair":
        task.update(
            instruction=view["instruction"].split(" Return one JSON object", 1)[0],
            original_source=view["source"],
            workspace_code_lines=_workspace(world, step, memory).splitlines(),
            test_index=[test["name"] for test in view["visible_tests"]],
            supported_python="Integer +, -, *, //, %, comparisons, boolean conditions, "
            "if/else, local assignments, returns, min/max/abs. Preserve the exact function "
            "and parameter names. No imports, loops, attributes or external calls.",
            submit_example={"action": "submit", "candidate": {"code_lines": [
                "def function_name(parameter):", "    return integer_expression"
            ]}},
        )
    else:
        instruction = view["instruction"].replace(
            "Answer using only the current closed documents below.",
            "Inspect current closed documents to answer."
        ).split(" Return one JSON object", 1)[0]
        task.update(
            instruction=instruction,
            source_index=[{"source_id": doc["source_id"], "version": doc["version"]}
                          for doc in view["documents"]],
            source_update_turn=4,
            submit_example={"action": "submit", "candidate": {
                "answer": {"lane": "lane_id", "max_units": 0},
                "citations": [{"source_id": "source_a", "version": 0},
                              {"source_id": "source_b", "version": 0}],
            }},
            citations_rule="Cite both current sources exactly once with source_id and integer version.",
        )
    return task


def messages_for(world, step, memory):
    task = _public_task(world, step, memory)
    receipts = [
        {key: record[key] for key in ("id", "agent", "step", "task_version", "valid", "feedback", "artifact")}
        for record in memory
    ]
    return [
        {"role": "system", "content": "Choose one action each turn. Return only one strict JSON "
         "object, without Markdown. Inspect with {\"action\":\"inspect\",\"target\":\"index_entry\"} "
         "or submit the candidate using the task's example schema. Examples contain placeholders, "
         "not answers. Inspections reveal a named test result or source document. Submitted code "
         "must use code_lines, one source line per string. Verified patches in visible receipts "
         "become your workspace. Prior receipts are the available shared work; use current source "
         "versions. You may freely choose inspect or submit on every turn; only a submitted "
         "candidate can complete the task. No other actions or extra fields are allowed."},
        {"role": "user", "content": _canonical({"task": task, "tool_receipts": receipts})},
    ]


def _artifact(world, step, kind, receipt):
    return {"data_version": DATA_VERSION, "world_id": world,
            "task_version": version(world, step), "kind": kind, "receipt": receipt}


def _inspect(world, step, memory, target):
    view = r3_tasks.public_view(world, _v1_step(step))
    if view["family"] == "code_repair":
        test = next((item for item in view["visible_tests"] if item["name"] == target), None)
        if test is None:
            raise ValueError("unknown test target; select a test_index entry")
        source = _workspace(world, step, memory)
        actual = _function(world, source)(test["arguments"])
        receipt = dict(test, actual=actual, passed=actual == test["expected"],
                       workspace_digest=sha256(source.encode()).hexdigest())
        feedback = "Test " + target + (" passed." if receipt["passed"] else " failed.")
        return feedback, _artifact(world, step, "test_receipt", receipt)
    document = next((doc for doc in view["documents"] if doc["source_id"] == target), None)
    if document is None:
        raise ValueError("unknown source target; select a source_index entry")
    return "Current document inspected.", _artifact(world, step, "source_receipt", document)


def _semantic_submit(world, candidate):
    if world in PUBLIC_PROBES:
        try:
            function = _function(world, _code(candidate))
            outputs = [function(arguments) for arguments in PUBLIC_PROBES[world]]
            return {"action": "submit", "kind": "code", "probe_outputs": outputs}
        except (ValueError, TypeError, RecursionError, OverflowError, ZeroDivisionError):
            return {"action": "submit", "kind": "code", "invalid": True}
    if type(candidate) is not dict or set(candidate) != {"answer", "citations"}:
        return {"action": "submit", "kind": "evidence", "invalid": True}
    return {"action": "submit", "kind": "evidence", "answer": deepcopy(candidate["answer"]),
            "citations": sorted(deepcopy(candidate["citations"]), key=_canonical)}


def apply(world, step, memory, text):
    """Execute exactly one declared action, without executing generated Python."""
    version(world, step)
    action = "invalid"
    semantic = {"action": "invalid", "invalid": True}
    try:
        if type(text) is not str or len(text) > 16_384:
            raise ValueError("action must be a JSON object within the text limit")
        request = json.loads(text, object_pairs_hook=r3_tasks._object,
                             parse_constant=r3_tasks._nonfinite)
        if type(request) is not dict:
            raise ValueError("action must be a JSON object")
        action = request.get("action", "invalid")
        if action == "inspect":
            if set(request) != {"action", "target"} or type(request["target"]) is not str:
                raise ValueError("inspect requires exactly action and string target")
            semantic = {"action": "inspect", "target": request["target"]}
            feedback, artifact = _inspect(world, step, memory, request["target"])
            return {"valid": True, "feedback": feedback, "artifact": artifact,
                    "action": action, "semantic_action": semantic}
        if action != "submit":
            raise ValueError("unknown action; choose inspect or submit")
        if set(request) != {"action", "candidate"} or type(request["candidate"]) is not dict:
            raise ValueError("submit requires exactly action and object candidate")
        candidate = request["candidate"]
        normalized = {"code": _code(candidate)} if world in PUBLIC_PROBES else candidate
        checked = r3_tasks.verify(world, _v1_step(step), _canonical(normalized))
        semantic = _semantic_submit(world, candidate) if checked["valid"] else {
            "action": "submit", "invalid": True
        }
        artifact = _artifact(world, step, "submitted_candidate", {
            "candidate": deepcopy(candidate), "verification": checked["artifact"]["verification"]
        }) if checked["valid"] else None
        return {"valid": checked["valid"], "feedback": checked["feedback"], "artifact": artifact,
                "action": action, "semantic_action": semantic}
    except (ValueError, TypeError, RecursionError, OverflowError, ZeroDivisionError) as exc:
        return {"valid": False, "feedback": "Invalid action: " + str(exc), "artifact": None,
                "action": action if type(action) is str else "invalid",
                "semantic_action": {"action": action if type(action) is str else "invalid", "invalid": True}}


def score(world, step, records):
    """Choose the latest current valid submission publicly, then score once."""
    selected = list(_eligible(world, step, records, "submitted_candidate"))
    if not selected:
        return False
    candidate = selected[-1]["artifact"]["receipt"]["candidate"]
    normalized = {"code": _code(candidate)} if world in PUBLIC_PROBES else candidate
    return r3_tasks.verify(world, _v1_step(step), _canonical(normalized), final=True)["valid"]
