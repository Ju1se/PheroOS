"""Finite public-tool tasks for coordination_repair_v1, never an authority API.

The trusted Session boundary must bind these pure tool values to actual settled
receipts. A content/provenance digest alone is neither execution authority nor
proof that a model obtained a receipt. Hidden objective lookup is used only by
``score`` after execution; the scripted reference reads public inputs only.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

DATA_VERSION = "coordination_repair_tasks_v1"
UPDATE_STEP = 2
ACTION_BYTES = 16_384
MATERIALIZED_CAP = 16
FAMILIES = ("interval_intersection", "dependency_readiness", "inventory_reconciliation", "version_correction")
FAILURE_STAGES = (
    "transport_format", "action_schema", "undeclared_target", "capability_permission",
    "missing_or_stale_evidence", "public_semantic_rejection", "runtime_lease_failure",
    "budget_deadline_stop", "hidden_final_objective_failure",
)

# These are input fixtures, not answer tables. Each family has two development
# instances and a separately named pilot instance fixed before model collection.
_INPUTS = {
    "interval_intersection/dev_a": {"lower": [2, 5], "upper": [11, 8], "preferred": 3},
    "interval_intersection/dev_b": {"lower": [-7, -4], "upper": [3, 6], "preferred": 8},
    "interval_intersection/pilot_a": {"lower": [4, 7], "upper": [15, 12], "preferred": 9},
    "dependency_readiness/dev_a": {"edges": {"atlas": [], "birch": ["atlas"], "cobalt": ["atlas"], "dune": ["birch", "cobalt"]}, "completed": ["atlas", "birch"]},
    "dependency_readiness/dev_b": {"edges": {"elm": [], "flint": [], "grove": ["elm", "flint"], "harbor": ["grove"]}, "completed": ["elm"]},
    "dependency_readiness/pilot_a": {"edges": {"iris": [], "jade": ["iris"], "kite": ["iris"], "lake": ["jade"], "moss": ["kite", "lake"]}, "completed": ["iris", "jade"]},
    "inventory_reconciliation/dev_a": {"opening": {"copper": 7, "zinc": 3}, "changes": [["e1", "b1", "copper", -2], ["e1", "b1", "copper", -2], ["e2", "b2", "zinc", 9], ["e3", "b1", "zinc", 4]], "approved": ["b1"]},
    "inventory_reconciliation/dev_b": {"opening": {"nickel": 10, "tin": 8}, "changes": [["e1", "b1", "nickel", 3], ["e2", "b2", "tin", -3], ["e3", "b1", "tin", 2], ["e2", "b2", "tin", -3]], "approved": ["b1", "b2"]},
    "inventory_reconciliation/pilot_a": {"opening": {"lead": 4, "silver": 12}, "changes": [["e1", "b7", "silver", -5], ["e2", "b8", "lead", 6], ["e3", "b7", "lead", 1], ["e3", "b7", "lead", 1]], "approved": ["b7"]},
    "version_correction/dev_a": {"query": "north", "before": {"north": 4, "south": 9}, "after": {"north": 11, "south": 3}},
    "version_correction/dev_b": {"query": "west", "before": {"east": 7, "west": 13}, "after": {"east": 5, "west": 2}},
    "version_correction/pilot_a": {"query": "center", "before": {"center": 6, "edge": 10}, "after": {"center": 14, "edge": 8}},
}

# Independent fixed expected outputs, deliberately outside public tool functions.
_EXPECTED = {
    "interval_intersection/dev_a": {1: {"selection": 5}},
    "interval_intersection/dev_b": {1: {"selection": 3}},
    "interval_intersection/pilot_a": {1: {"selection": 9}},
    "dependency_readiness/dev_a": {1: {"ready": ["cobalt"]}},
    "dependency_readiness/dev_b": {1: {"ready": ["flint"]}},
    "dependency_readiness/pilot_a": {1: {"ready": ["kite", "lake"]}},
    "inventory_reconciliation/dev_a": {1: {"totals": {"copper": 5, "zinc": 7}}},
    "inventory_reconciliation/dev_b": {1: {"totals": {"nickel": 13, "tin": 7}}},
    "inventory_reconciliation/pilot_a": {1: {"totals": {"lead": 5, "silver": 7}}},
    "version_correction/dev_a": {1: {"value": 4}, 2: {"value": 11}},
    "version_correction/dev_b": {1: {"value": 13}, 2: {"value": 2}},
    "version_correction/pilot_a": {1: {"value": 6}, 2: {"value": 14}},
}


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return "sha256:" + sha256(_wire(value).encode()).hexdigest()


def worlds(split="development"):
    """Return the predeclared disjoint eight-development/four-pilot split."""
    if split not in ("development", "pilot"):
        raise ValueError("split must be development or pilot")
    return [w for w in _INPUTS if ("/dev_" in w) == (split == "development")]


def _check(world, step):
    if type(world) is not str or world not in _INPUTS:
        raise ValueError("undeclared world")
    if type(step) is not int or step < 0:
        raise ValueError("step must be a nonnegative integer")


def _version(world, step):
    return 2 if world.startswith("version_correction/") and step >= UPDATE_STEP else 1


def _documents(world, version):
    x = _INPUTS[world]
    family = world.split("/")[0]
    if family == "interval_intersection":
        docs = {"lower_bounds": {"bounds": x["lower"]}, "upper_bounds": {"bounds": x["upper"]}, "preference": {"preferred": x["preferred"]}}
    elif family == "dependency_readiness":
        docs = {"dependency_graph": {"dependencies": x["edges"]}, "completion_state": {"completed": x["completed"]}}
    elif family == "inventory_reconciliation":
        docs = {"opening_balances": {"balances": x["opening"]}, "change_events": {"events": [dict(zip(("event_id", "batch", "item", "delta"), row)) for row in x["changes"]]}, "approved_batches": {"batches": x["approved"]}}
    else:
        docs = {"current_values": {"values": x["before" if version == 1 else "after"]}}
    # A genuine unrelated source with no claims about the task's required facts.
    docs["unrelated_notice"] = {"subject": "archive_label", "label": "circular", "task_evidence": False}
    return docs


def _source_version(world, version, source):
    return version if world.startswith("version_correction/") and source == "current_values" else 1


def public_world(world, step):
    """Public rules, concrete legal targets, source versions and acquisition DAG.

    No source content or expected answer is included. D0/D1 may pin their task
    step to UPDATE_STEP from the start; preparation still uses charged tools.
    """
    _check(world, step)
    family, version = world.split("/")[0], _version(world, step)
    rules = {
        "interval_intersection": "Take the maximum lower bound and minimum upper bound. Select the allowed integer nearest the preferred integer (clamp preference to that interval).",
        "dependency_readiness": "Return the sorted IDs of unfinished tasks whose declared dependencies are all completed. Completion does not propagate without an explicit completed entry.",
        "inventory_reconciliation": "Start from opening balances. Include changes only from approved batches. Count each event_id once, even if delivered repeatedly. Sum the distinct included deltas by item.",
        "version_correction": "Read the requested key from the current version of current_values. Old versions remain historical and cannot establish the current answer.",
    }
    answer_schemas = {
        "interval_intersection": {"selection": "integer"},
        "dependency_readiness": {"ready": "array of unique task ID strings"},
        "inventory_reconciliation": {"totals": "object mapping each declared item ID to integer"},
        "version_correction": {"value": "integer"},
    }
    sources = [{"source_id": s, "source_version": _source_version(world, version, s), "required": s != "unrelated_notice"}
               for s in _documents(world, version)]
    required = [s["source_id"] for s in sources if s["required"]]
    dag = [{"task_id": "inspect:" + s, "dependencies": [], "target": s} for s in required]
    dag.append({"task_id": "submit", "dependencies": ["inspect:" + s for s in required]})
    out = {"data_version": DATA_VERSION, "world_id": world, "family": family, "step": step,
           "task_version": version, "sources": sources, "rule": rules[family], "work_dag": dag,
           "public_stop_rule": "Stop after a current-version public-accepted submission, once any declared source update has occurred; hidden correctness never controls stopping.",
           "update_step": UPDATE_STEP if family == "version_correction" else None,
           "action_schema": {"inspect": {"required_fields": ["action", "target"], "target_enum": [s["source_id"] for s in sources]},
                             "submit": {"required_fields": ["action", "answer", "citations"], "answer": answer_schemas[family],
                                        "citations": "one object per required source, exactly source_id and source_version from a current materialized receipt"},
                             "extra_fields": False},
           "legal_inspections": [{"action": "inspect", "target": s["source_id"]} for s in sources]}
    if family == "version_correction":
        out["requested_key"] = _INPUTS[world]["query"]
    elif family == "inventory_reconciliation":
        out["item_ids"] = sorted(_INPUTS[world]["opening"])
    elif family == "dependency_readiness":
        out["task_ids"] = sorted(_INPUTS[world]["edges"])
    return deepcopy(out)


def inspect(world, step, target):
    """Pure inspection result. Call through the same metered tool in every arm."""
    _check(world, step)
    version = _version(world, step)
    docs = _documents(world, version)
    if type(target) is not str or target not in docs:
        raise ValueError("undeclared source target")
    base = {"data_version": DATA_VERSION, "kind": "source_receipt", "world_id": world,
            "source_id": target, "source_version": _source_version(world, version, target), "content": deepcopy(docs[target])}
    base["receipt_identity"] = _digest(base)
    return base


def verify_artifact(world, artifact):
    """Check immutable fixture bytes and provenance, including historical versions.

    This pure verifier has a concrete Session tool-verification caller. Callers
    must separately establish settled tool receipt lineage, access and authority.
    """
    try:
        _check(world, 0)
        if type(artifact) is not dict or set(artifact) != {"data_version", "kind", "world_id", "source_id", "source_version", "content", "receipt_identity"}:
            return False
        version = artifact["source_version"]
        if type(version) is not int or version not in (1, 2):
            return False
        source = artifact["source_id"]
        expected = inspect(world, UPDATE_STEP if version == 2 else 0, source)
        return _wire(artifact) == _wire(expected)
    except (TypeError, ValueError, KeyError):
        return False


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("non-finite JSON number")


def _parse(raw):
    if type(raw) is not str or len(raw.encode()) > ACTION_BYTES:
        raise ValueError("action must be a bounded JSON string")
    text = raw.strip()
    framing = "plain_json"
    if text.startswith("```json\n") and text.endswith("\n```") and text.count("```") == 2:
        text, framing = text[8:-4], "single_json_fence"
    return json.loads(text, object_pairs_hook=_object, parse_constant=_nonfinite), framing


def _answer_schema(view, answer):
    if type(answer) is not dict:
        return False
    family = view["family"]
    bounded = lambda v: type(v) is int and abs(v) <= 10**9
    if family in ("interval_intersection", "version_correction"):
        key = "selection" if family == "interval_intersection" else "value"
        return set(answer) == {key} and bounded(answer[key])
    if family == "dependency_readiness":
        if set(answer) != {"ready"} or type(answer["ready"]) is not list:
            return False
        ready = answer["ready"]
        return all(type(v) is str and v in view["task_ids"] for v in ready) and len(set(ready)) == len(ready)
    return (set(answer) == {"totals"} and type(answer["totals"]) is dict
            and set(answer["totals"]) == set(view["item_ids"])
            and all(bounded(v) for v in answer["totals"].values()))


def _citation(artifact):
    return {k: artifact[k] for k in ("source_id", "source_version")}


def parse_action(world, step, raw):
    """Syntax/schema/legal-target validation only; never execute an inspection.

    All arms meter this same validation. Candidate reuse may then avoid the pure
    inspection dispatch without first executing that inspection during parsing.
    """
    view = public_world(world, step)
    result = {"valid": False, "stage": "transport_format", "feedback": "", "artifact": None,
              "normalized_action": None, "framing": None}
    try:
        action, framing = _parse(raw)
        result.update(normalized_action=deepcopy(action), framing=framing)
    except (ValueError, TypeError, RecursionError) as exc:
        result["feedback"] = "Return one JSON object: " + str(exc)
        return result
    result["stage"] = "action_schema"
    if type(action) is not dict:
        result["feedback"] = "Action must be an object with a declared action name."
        return result
    if action.get("action") == "inspect":
        if set(action) != {"action", "target"} or type(action["target"]) is not str:
            result["feedback"] = "Inspect requires exactly action and a target string."
            return result
        if action["target"] not in view["action_schema"]["inspect"]["target_enum"]:
            result.update(stage="undeclared_target", feedback="Choose a target from the public source IDs.")
            return result
    elif action.get("action") == "submit":
        if set(action) != {"action", "answer", "citations"} or not _answer_schema(view, action.get("answer")):
            result["feedback"] = "Submit requires exactly action, a declared answer shape, and citations."
            return result
        citations = action["citations"]
        if (type(citations) is not list or len(citations) > 4
                or any(type(c) is not dict or set(c) != {"source_id", "source_version"}
                       or type(c["source_id"]) is not str or type(c["source_version"]) is not int
                       for c in citations)):
            result["feedback"] = "Citations are objects containing exactly source_id and integer source_version."
            return result
    else:
        result["feedback"] = "Action must be inspect or submit."
        return result
    result.update(valid=True, stage="accepted", feedback="Public action syntax accepted; no tool was executed.")
    return result


def execute(world, step, raw, materialized):
    """Execute a parsed public action, never hidden correctness or authority.

    ``materialized`` must contain only artifacts retrieved by the trusted runtime
    under this branch's access rights. Invalid model actions remain failed rows.
    Actual settled receipt identity is retained in the submission artifact; the
    model cites short source/version pairs instead of copying large digest text.
    """
    view = public_world(world, step)
    result = parse_action(world, step, raw)
    if not result["valid"]:
        return result
    result["valid"] = False
    action = result["normalized_action"]
    if action["action"] == "inspect":
        artifact = inspect(world, step, action["target"])
    else:
        citations = action["citations"]
        result["stage"] = "missing_or_stale_evidence"
        if type(materialized) is not list or len(materialized) > MATERIALIZED_CAP or any(not verify_artifact(world, r) for r in materialized):
            result["feedback"] = "Materialized evidence failed the trusted artifact boundary."
            return result
        required = [s for s in view["sources"] if s["required"]]
        current = []
        for source in required:
            matches = [r for r in materialized if r["source_id"] == source["source_id"] and r["source_version"] == source["source_version"]]
            if not matches:
                result["feedback"] = "Retrieve each required current source before submitting."
                return result
            current.append(matches[0])
        expected = sorted((_citation(r) for r in current), key=_wire)
        if type(citations) is not list or _wire(sorted(citations, key=_wire)) != _wire(expected):
            result["feedback"] = "Cite each required current source and version exactly once."
            return result
        artifact = {"data_version": DATA_VERSION, "kind": "submission", "world_id": world,
                    "task_version": view["task_version"], "answer": deepcopy(action["answer"]),
                    "citations": deepcopy(expected),
                    "evidence_receipt_identities": [r["receipt_identity"] for r in current]}
        artifact["receipt_identity"] = _digest(artifact)
    result.update(valid=True, stage="accepted", feedback="Public action accepted; hidden objective was not evaluated.", artifact=artifact)
    return result


def score(world, step, submission):
    """Hidden final objective, called only by the independent post-run evaluator."""
    _check(world, step)
    if type(submission) is not dict:
        return False
    if (submission.get("world_id") != world or submission.get("kind") != "submission"
            or type(submission.get("task_version")) is not int
            or submission["task_version"] != _version(world, step)):
        return False
    answer = submission.get("answer")
    if type(answer) is not dict:
        return False
    # Order of a ready set has no objective significance, while the public rule
    # requests sorted serialization. This evaluator independently normalizes it.
    if world.startswith("dependency_readiness/") and type(answer.get("ready")) is list:
        answer = {**answer, "ready": sorted(answer["ready"])}
    return _wire(answer) == _wire(_EXPECTED[world][_version(world, step)])


def reference_action(public_view, materialized):
    """Trusted instrument policy deriving actions only from its public arguments.

    It does not access _INPUTS, _EXPECTED, inspect, verify_artifact or score.
    Runtime execution must meter every returned inspect/submit action normally.
    """
    docs = {}
    for source in public_view["sources"]:
        if not source["required"]:
            continue
        available = [r for r in materialized if r["source_id"] == source["source_id"] and r["source_version"] == source["source_version"]]
        if not available:
            return {"action": "inspect", "target": source["source_id"]}
        docs[source["source_id"]] = available[0]
    content = {k: v["content"] for k, v in docs.items()}
    family = public_view["family"]
    if family == "interval_intersection":
        low = max(content["lower_bounds"]["bounds"])
        high = min(content["upper_bounds"]["bounds"])
        answer = {"selection": min(max(content["preference"]["preferred"], low), high)}
    elif family == "dependency_readiness":
        completed = set(content["completion_state"]["completed"])
        answer = {"ready": sorted(t for t, deps in content["dependency_graph"]["dependencies"].items() if t not in completed and all(d in completed for d in deps))}
    elif family == "inventory_reconciliation":
        totals = dict(content["opening_balances"]["balances"])
        approved, seen = set(content["approved_batches"]["batches"]), set()
        for event in content["change_events"]["events"]:
            if event["event_id"] not in seen and event["batch"] in approved:
                totals[event["item"]] += event["delta"]
                seen.add(event["event_id"])
        answer = {"totals": totals}
    elif family == "version_correction":
        answer = {"value": content["current_values"]["values"][public_view["requested_key"]]}
    else:
        raise ValueError("undeclared public rule family")
    return {"action": "submit", "answer": answer,
            "citations": [{k: r[k] for k in ("source_id", "source_version")} for r in docs.values()]}
