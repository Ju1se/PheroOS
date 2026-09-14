"""Experimental 32-turn R4 fixtures and bounded receipt visibility policies.

These new development worlds are not independent evidence about capability.
Public action validation never calls the hidden scorer. The only reused R3
implementation is its frozen, non-executing bounded integer interpreter.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .r3_tasks import _IntegerFunction, _nonfinite, _object


DATA_VERSION = "r4_task_fixtures_v1"
STEPS, HISTORY_CAP, SELECTED_CAP, TTL = 32, 32, 4, 8
POLICIES = ("private", "blackboard", "dedup_ttl", "versioned")
_WORLDS = (
    "code_repair/bounded_increment", "code_repair/cyclic_offset",
    "evidence_revision/route_quota", "evidence_revision/ready_window",
)
_CODE = {
    _WORLDS[0]: dict(
        name="bounded_increment", arguments=["value", "increment", "ceiling"],
        instruction="Repair bounded_increment(value, increment, ceiling). Inputs are integers "
        "with 0 <= value <= ceiling and increment >= 0. Increase value by increment, "
        "but return ceiling if the increase would exceed ceiling.",
        source="def bounded_increment(value, increment, ceiling):\n    return value + increment",
        tests=[("below_ceiling", [2, 3, 8], 5), ("cross_ceiling", [7, 2, 8], 8),
               ("zero_increment", [4, 0, 8], 4)]),
    _WORLDS[1]: dict(
        name="cyclic_offset", arguments=["start", "distance", "size"],
        instruction="Repair cyclic_offset(start, distance, size). Inputs are integers; size "
        "is positive and 0 <= start < size. Move distance positions around a ring of size "
        "positions, allowing negative distance. Return the final index from 0 through size - 1.",
        source="def cyclic_offset(start, distance, size):\n    return start + distance",
        tests=[("inside_ring", [2, 3, 10], 5), ("wrap_forward", [9, 3, 10], 2),
               ("wrap_backward", [1, -3, 10], 8)]),
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return sha256(_canonical(value).encode()).hexdigest()


def world_ids():
    return list(_WORLDS)


def _step(step):
    if type(step) is not int or not 0 <= step < STEPS:
        raise ValueError("step must be an integer from zero through 31")


def task_version(world, step):
    _step(step)
    if type(world) is not str or world not in _WORLDS:
        raise ValueError("undeclared R4 world")
    return _version(world, step)


def _version(world, step):
    return 1 if world in _CODE or step < 16 else 2


def _documents(world, version):
    if world == _WORLDS[2]:
        contents = {
            "route_policy": {"selected_lane": "amber", "request_limit": 7 if version == 1 else 5},
            "route_capacity": {"amber": 9, "violet": 4} if version == 1 else {"amber": 4, "violet": 10},
            "route_ceiling": {"amber": 6, "violet": 3} if version == 1 else {"amber": 3, "violet": 8},
        }
    elif world == _WORLDS[3]:
        contents = {
            "ready_policy": {"required_state": "ready", "request_limit": 7 if version == 1 else 6,
                             "tie_break": "lexicographically smallest qualifying lane ID"},
            "ready_state": {"cedar": "ready", "delta": "hold"} if version == 1 else {"cedar": "hold", "delta": "ready"},
            "ready_limits": {"cedar": {"capacity": 6, "ceiling": 4}, "delta": {"capacity": 9, "ceiling": 8}}
            if version == 1 else {"cedar": {"capacity": 8, "ceiling": 5}, "delta": {"capacity": 7, "ceiling": 5}},
        }
    else:
        raise ValueError("code worlds have no document sources")
    return [dict(source_id=key, version=version, content=value) for key, value in contents.items()]


def _origin(artifact):
    try:
        receipt, kind = artifact["receipt"], artifact["kind"]
        if kind == "source_receipt":
            claim = {key: receipt[key] for key in ("source_id", "version")}
        elif kind == "test_receipt":
            claim = {key: receipt[key] for key in ("name", "workspace_digest")}
        elif kind == "submitted_candidate":
            claim = receipt["candidate"]
        else:
            raise ValueError("undeclared artifact kind")
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid artifact provenance") from exc
    return _digest([DATA_VERSION, artifact["world_id"], artifact["task_version"], kind, claim])


def _records(records, step, *, current=False):
    """One episode's bounded trusted tool history; model text is never a record."""
    _step(step)
    if type(records) is not list or len(records) > HISTORY_CAP:
        raise ValueError("history exceeds the global 32-record cap")
    worlds, steps = set(), set()
    for record in records:
        if type(record) is not dict:
            raise ValueError("record must be an object")
        world, previous = record.get("world_id"), record.get("step")
        version = task_version(world, previous)
        if (previous > step or (previous == step and not current) or previous in steps
                or record.get("task_version") != version or type(record.get("task_version")) is not int
                or type(record.get("agent")) is not str or not record["agent"]
                or type(record.get("valid")) is not bool or type(record.get("feedback")) is not str
                or type(record.get("origin_identity")) is not str or not record["origin_identity"]):
            raise ValueError("invalid or noncausal record")
        artifact = record.get("artifact")
        if record["valid"]:
            if (type(artifact) is not dict or set(artifact) != {
                    "data_version", "world_id", "task_version", "kind", "receipt"}
                    or artifact["data_version"] != DATA_VERSION or artifact["world_id"] != world
                    or artifact["task_version"] != version or type(artifact["task_version"]) is not int
                    or type(artifact["receipt"]) is not dict or record["origin_identity"] != _origin(artifact)):
                raise ValueError("invalid artifact lineage")
        elif artifact is not None:
            raise ValueError("invalid action cannot carry an evidence artifact")
        worlds.add(world)
        steps.add(previous)
    if len(worlds) > 1 or [r["step"] for r in records] != sorted(steps):
        raise ValueError("history must be chronological and belong to one world")
    return records


def select(policy, records, agent, step, task_version):
    previous = _records(records, step)
    if (policy not in POLICIES or type(agent) is not str or not agent
            or type(task_version) is not int or task_version not in (1, 2)):
        raise ValueError("invalid selection declaration")
    if previous and _version(previous[0]["world_id"], step) != task_version:
        raise ValueError("selection version is not current")
    if policy == "private":
        previous = [r for r in previous if r["agent"] == agent]
    elif policy in ("dedup_ttl", "versioned"):
        previous = [r for r in previous if step - r["step"] < TTL]
    if policy == "versioned":
        previous = [r for r in previous if r["task_version"] == task_version]
    selected, seen = [], set()
    for record in reversed(previous):
        origin = record["origin_identity"]
        if policy in ("dedup_ttl", "versioned") and origin in seen:
            continue
        seen.add(origin)
        selected.append(record)
        if len(selected) == SELECTED_CAP:
            break
    return deepcopy(list(reversed(selected)))


def _memory(world, step, records):
    _records(records, step)
    if len(records) > SELECTED_CAP or any(r["world_id"] != world for r in records):
        raise ValueError("selected memory must contain at most four same-world records")


def _eligible(world, step, records, kind):
    return [r for r in records if r["valid"] and r["world_id"] == world
            and r["task_version"] == task_version(world, step) and r["artifact"]["kind"] == kind]


def _code(candidate):
    if type(candidate) is not dict or set(candidate) != {"code_lines"}:
        raise ValueError("code candidate requires exactly code_lines")
    lines = candidate["code_lines"]
    if (type(lines) is not list or not lines or any(type(line) is not str for line in lines)
            or any("\n" in line or "\r" in line for line in lines)):
        raise ValueError("code_lines must contain one source line per string")
    return "\n".join(lines)


def _function(world, code):
    spec = _CODE[world]
    return _IntegerFunction(code, spec["name"], spec["arguments"])


def _workspace(world, step, records):
    candidates = _eligible(world, step, records, "submitted_candidate")
    return _code(candidates[-1]["artifact"]["receipt"]["candidate"]) if candidates else _CODE[world]["source"]


def messages_for(world, step, selected_records):
    version = task_version(world, step)
    _memory(world, step, selected_records)
    task = dict(data_version=DATA_VERSION, world_id=world, task_version=version,
                turn=step + 1, total_turns=STEPS)
    if world in _CODE:
        spec = _CODE[world]
        task.update(instruction=spec["instruction"], original_source=spec["source"],
                    workspace_code_lines=_workspace(world, step, selected_records).splitlines(),
                    test_index=[test[0] for test in spec["tests"]],
                    supported_python="Integer + - * // %, comparisons, boolean conditions, if/else, "
                    "local assignments, return, min/max/abs. Preserve exact function and parameters. "
                    "No imports, loops, attributes, or external calls.",
                    submit_example={"action": "submit", "candidate": {"code_lines": [
                        "def function_name(parameter):", "    return integer_expression"]}})
    else:
        rule = ("Select route_policy.selected_lane. max_units is the minimum of its request_limit "
                "and that lane's route_capacity and route_ceiling." if world == _WORLDS[2] else
                "Use ready_policy.required_state and ready_state to choose a lane; apply the declared "
                "tie_break. max_units is the minimum of ready_policy.request_limit and the chosen "
                "lane's ready_limits.capacity and ready_limits.ceiling.")
        task.update(instruction="Inspect all three current sources and combine them. " + rule,
                    source_index=[{key: doc[key] for key in ("source_id", "version")}
                                  for doc in _documents(world, version)], source_update_turn=17,
                    citations_rule="Cite all three current sources exactly once. Each must have an "
                    "actual current inspection receipt in the available tool receipts.",
                    submit_example={"action": "submit", "candidate": {
                        "answer": {"lane": "lane_id", "max_units": 0},
                        "citations": [{key: doc[key] for key in ("source_id", "version")}
                                      for doc in _documents(world, version)]}})
    # No identity/agent labels: complete shared visibility is invariant to N.
    receipts = [{key: r[key] for key in ("step", "task_version", "valid", "feedback", "artifact")}
                for r in selected_records]
    return [{"role": "system", "content": "Choose one action each turn. Return only one strict JSON "
             "object, without Markdown. Inspect with {\"action\":\"inspect\",\"target\":\"index_entry\"}, "
             "or submit using the task's candidate schema. Placeholder values are not answers. Code uses "
             "code_lines, one source line per string. Prior tool receipts are your available work. "
             "Only a submitted candidate can complete the task. Use current versions. Public action "
             "acceptance does not establish final correctness. No other actions or extra fields."},
            {"role": "user", "content": _canonical({"task": task, "tool_receipts": receipts})}]


def _artifact(world, step, kind, receipt):
    return dict(data_version=DATA_VERSION, world_id=world, task_version=task_version(world, step),
                kind=kind, receipt=receipt)


def _inspect(world, step, records, target):
    if world in _CODE:
        spec = next((t for t in _CODE[world]["tests"] if t[0] == target), None)
        if spec is None:
            raise ValueError("unknown test target")
        name, arguments, expected = spec
        code = _workspace(world, step, records)
        actual = _function(world, code)(arguments)
        return _artifact(world, step, "test_receipt", dict(name=name, arguments=arguments,
            expected=expected, actual=actual, passed=actual == expected, workspace_digest=_digest(code)))
    document = next((d for d in _documents(world, task_version(world, step)) if d["source_id"] == target), None)
    if document is None:
        raise ValueError("unknown source target")
    return _artifact(world, step, "source_receipt", document)


def _submit(world, step, records, candidate):
    if world in _CODE:
        function = _function(world, _code(candidate))
        outputs = [function(arguments) for _, arguments, _ in _CODE[world]["tests"]]
        if any(type(actual) is not int or actual != test[2] for actual, test in zip(outputs, _CODE[world]["tests"])):
            raise ValueError("candidate fails a declared public test; inspect test_index entries")
        return dict(candidate=deepcopy(candidate), public_test_outputs=outputs)
    if type(candidate) is not dict or set(candidate) != {"answer", "citations"}:
        raise ValueError("evidence candidate requires exactly answer and citations")
    answer, citations = candidate["answer"], candidate["citations"]
    if (type(answer) is not dict or set(answer) != {"lane", "max_units"}
            or type(answer["lane"]) is not str or not answer["lane"]
            or type(answer["max_units"]) is not int or not 0 <= answer["max_units"] <= 10**12):
        raise ValueError("answer requires a lane string and bounded nonnegative integer max_units")
    documents = _documents(world, task_version(world, step))
    expected = [{key: doc[key] for key in ("source_id", "version")} for doc in documents]
    if (type(citations) is not list or len(citations) != 3
            or any(type(c) is not dict or set(c) != {"source_id", "version"}
                   or type(c["source_id"]) is not str or type(c["version"]) is not int for c in citations)
            or sorted(citations, key=_canonical) != sorted(expected, key=_canonical)):
        raise ValueError("cite all three exact current sources once")
    inspected = [r["artifact"]["receipt"] for r in _eligible(world, step, records, "source_receipt")]
    if any(not any(_canonical(doc) == _canonical(receipt) for receipt in inspected) for doc in documents):
        raise ValueError("all three current source inspection receipts are required")
    return dict(candidate=deepcopy(candidate), source_origins=[_origin(_artifact(world, step, "source_receipt", d))
                                                              for d in documents])


def apply(world, step, selected_records, text):
    """Validate normalized strict JSON and execute a public deterministic tool."""
    version = task_version(world, step)
    _memory(world, step, selected_records)
    action = "invalid"
    try:
        if type(text) is not str or len(text.encode()) > 16_384:
            raise ValueError("action must be a bounded strict JSON object")
        request = json.loads(text, object_pairs_hook=_object, parse_constant=_nonfinite)
        if type(request) is not dict:
            raise ValueError("action must be an object")
        action = request.get("action", "invalid")
        if action == "inspect" and set(request) == {"action", "target"} and type(request["target"]) is str:
            artifact = _inspect(world, step, selected_records, request["target"])
            semantic = dict(action=action, target=request["target"])
            feedback = "Public inspection completed."
        elif action == "submit" and set(request) == {"action", "candidate"} and type(request["candidate"]) is dict:
            receipt = _submit(world, step, selected_records, request["candidate"])
            artifact = _artifact(world, step, "submitted_candidate", receipt)
            semantic = (dict(action=action, public_test_outputs=receipt["public_test_outputs"])
                        if world in _CODE else dict(action=action, answer=deepcopy(request["candidate"]["answer"]),
                            citations=sorted(deepcopy(request["candidate"]["citations"]), key=_canonical)))
            feedback = "Public candidate checks accepted; hidden correctness was not checked."
        else:
            raise ValueError("choose exactly inspect with target or submit with candidate")
        return dict(world_id=world, task_version=version, valid=True, feedback=feedback, artifact=artifact,
                    action=action, semantic_action=semantic, origin_identity=_origin(artifact))
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError, ZeroDivisionError) as exc:
        action = action if type(action) is str else "invalid"
        return dict(world_id=world, task_version=version, valid=False, feedback="Invalid action: " + str(exc),
                    artifact=None, action=action, semantic_action={"action": action, "invalid": True},
                    origin_identity=_digest([world, version, "invalid", text if type(text) is str else None]))


def score(world, step, records):
    """Select the latest current valid submission, then apply hidden checks."""
    task_version(world, step)
    _records(records, step, current=True)
    if any(r["world_id"] != world for r in records):
        raise ValueError("scorer history belongs to another world")
    selected = _eligible(world, step, records, "submitted_candidate")
    if not selected:
        return False
    candidate = selected[-1]["artifact"]["receipt"]["candidate"]
    if world in _CODE:
        try:
            function = _function(world, _code(candidate))
            visible = {tuple(test[1]) for test in _CODE[world]["tests"]}
            if world == _WORLDS[0]:
                cases = ((value, increase, ceiling) for ceiling in range(0, 13)
                         for value in range(ceiling + 1) for increase in range(0, 16))
                expected = lambda args: min(args[0] + args[1], args[2])
            else:
                cases = ((start, distance, size) for size in range(1, 10)
                         for start in range(size) for distance in range(-15, 16))
                expected = lambda args: (args[0] + args[1]) % args[2]
            return all(type(actual := function(list(args))) is int and actual == expected(args)
                       for args in cases if args not in visible)
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError, ZeroDivisionError):
            return False
    # Hidden fixed answer table is independent of the public schema/provenance checker.
    truth = {(_WORLDS[2], 1): ("amber", 6), (_WORLDS[2], 2): ("amber", 3),
             (_WORLDS[3], 1): ("cedar", 4), (_WORLDS[3], 2): ("delta", 5)}
    lane, units = truth[world, task_version(world, step)]
    return candidate["answer"] == {"lane": lane, "max_units": units}
