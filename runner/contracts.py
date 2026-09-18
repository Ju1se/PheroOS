"""Validated records for bounded agent orchestration.

Workflow specs, agents, tasks, proposals, artifacts, decisions and outcomes are
canonical dictionaries produced by the validators below, plus a bounded finite-JSON
schema checker. Nothing here has behaviour beyond validation, canonical
serialization and digests. Natural-language fields are bounded opaque text and
grant nothing; an identifier in model output is data until the host resolves it
against a declaration.
"""

from hashlib import sha256
import json
import math
import re

SPEC_FORMAT = "orchestration-workflow-v2"
LEGACY_SPEC_FORMAT = "orchestration-workflow-v1"
SPEC_FORMATS = (LEGACY_SPEC_FORMAT, SPEC_FORMAT)
OUTCOME_FORMAT = "orchestration-outcome-v1"
TEMPLATE_VERSION = "orchestration-context-v1"
MODEL_TOOL_REF = "model.anthropic-messages"
HOST_AGENT = "host"
PROVIDERS = ("fake", "anthropic")
TASK_KINDS = ("model", "host")
RULES = ("checker_pass",)
RESERVED_TOOLS = ("submit_output", "abstain", "propose_children")
OUTCOMES = ("success", "rejected", "abstained", "dependency_failed", "budget_exhausted",
            "cancelled", "blocked_unknown", "error")
SCHEMA_TYPES = ("object", "array", "string", "integer", "number", "boolean", "null")
MAX_DEPTH = 32
MAX_SCHEMA_DEPTH = 8
MAX_SCHEMA_BYTES = 8192
MAX_INSTRUCTIONS = 8192
MAX_REASON = 1024
NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


class ContractError(ValueError):
    """A record, schema or proposal failed validation; a data error, never an instruction."""


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(wire(value).encode()).hexdigest()


def finite_json(value, depth=0):
    """Copy a finite JSON value with string keys and bounded nesting; reject anything else."""
    if depth > MAX_DEPTH:
        raise ContractError("JSON nesting exceeds bound")
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ContractError("JSON object keys must be strings")
        return {key: finite_json(item, depth + 1) for key, item in value.items()}
    if type(value) is list:
        return [finite_json(item, depth + 1) for item in value]
    if type(value) is float:
        if not math.isfinite(value):
            raise ContractError("finite JSON numbers required")
        return value
    if value is None or type(value) in (str, int, bool):
        return value
    raise ContractError("JSON values required")


def _text(value, name, maximum):
    if type(value) is not str or not value.strip() or len(value.encode()) > maximum:
        raise ContractError(f"{name} must be nonempty text of at most {maximum} bytes")
    return value


def _name(value, name):
    if type(value) is not str or not NAME.match(value):
        raise ContractError(f"{name} must match {NAME.pattern}")
    return value


def _count(value, name, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        bound = f" and <= {maximum}" if maximum is not None else ""
        raise ContractError(f"{name} must be an exact integer >= {minimum}{bound}")
    return value


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ContractError(f"{name} must be a finite number")
    return value


def _names(values, name, maximum=64):
    if type(values) is not list or len(values) > maximum or len(set(values)) != len(values):
        raise ContractError(f"{name} must be a bounded list of distinct names")
    return [_name(value, name) for value in values]


def _fields(value, name, required, optional=()):
    if type(value) is not dict:
        raise ContractError(f"{name} must be an object")
    keys = set(value)
    if not set(required) <= keys or keys - set(required) - set(optional):
        raise ContractError(f"{name} requires exactly {sorted(required)} plus optional {sorted(optional)}")
    return value


# ---------------------------------------------------------------- schemas

def validate_schema(schema, depth=0):
    """A bounded JSON-Schema subset: closed objects, bounded arrays and strings, finite numbers."""
    if depth > MAX_SCHEMA_DEPTH:
        raise ContractError("schema nesting exceeds bound")
    if type(schema) is not dict or type(schema.get("type")) is not str or schema["type"] not in SCHEMA_TYPES:
        raise ContractError("schema needs one supported type")
    kind = schema["type"]
    allowed = {"type", "description"}
    out = {"type": kind}
    if "description" in schema:
        out["description"] = _text(schema["description"], "schema description", 1024)
    if kind == "object":
        allowed |= {"properties", "required", "additionalProperties"}
        properties = schema.get("properties", {})
        if type(properties) is not dict or len(properties) > 64:
            raise ContractError("object schema needs a bounded properties map")
        out["properties"] = {}
        for key, item in properties.items():
            if type(key) is not str or not key or len(key) > 64:
                raise ContractError("property names must be short strings")
            out["properties"][key] = validate_schema(item, depth + 1)
        required = schema.get("required", [])
        if (type(required) is not list or len(set(required)) != len(required)
                or not set(required) <= set(out["properties"])):
            raise ContractError("required must list distinct declared properties")
        out["required"] = list(required)
        if schema.get("additionalProperties", False) is not False:
            raise ContractError("object schemas are closed: additionalProperties must be false")
        out["additionalProperties"] = False
    elif kind == "array":
        allowed |= {"items", "maxItems", "minItems"}
        if "items" not in schema:
            raise ContractError("array schema needs items")
        out["items"] = validate_schema(schema["items"], depth + 1)
        out["maxItems"] = _count(schema.get("maxItems"), "maxItems", 0, 4096)
        out["minItems"] = _count(schema.get("minItems", 0), "minItems", 0, out["maxItems"])
    elif kind == "string":
        allowed |= {"maxLength", "minLength", "enum"}
        if "enum" in schema:
            enum = schema["enum"]
            if (type(enum) is not list or not enum or len(enum) > 64 or len(set(enum)) != len(enum)
                    or any(type(item) is not str or len(item) > 256 for item in enum)):
                raise ContractError("enum must list distinct short strings")
            out["enum"] = list(enum)
        if "maxLength" not in schema and "enum" not in schema:
            # An unbounded string would be silently narrowed to length zero, which makes
            # every value unsatisfiable. Require the bound, as the array branch does.
            raise ContractError("a string schema needs an explicit maxLength or an enum")
        out["maxLength"] = _count(schema.get("maxLength", max(len(item) for item in out.get("enum", [""]))),
                                  "maxLength", 0, 65536)
        out["minLength"] = _count(schema.get("minLength", 0), "minLength", 0, out["maxLength"])
    elif kind in ("integer", "number"):
        allowed |= {"minimum", "maximum"}
        for bound in ("minimum", "maximum"):
            if bound in schema:
                out[bound] = _number(schema[bound], bound)
        if "minimum" in out and "maximum" in out and out["minimum"] > out["maximum"]:
            raise ContractError("minimum exceeds maximum")
    if set(schema) - allowed:
        raise ContractError("unsupported schema keyword: " + ", ".join(sorted(set(schema) - allowed)))
    if depth == 0 and len(wire(out).encode()) > MAX_SCHEMA_BYTES:
        raise ContractError("schema exceeds byte bound")
    return out


def conforms(schema, value, path="$"):
    """Return None when value conforms to a validated schema, else the first error as text."""
    kind = schema["type"]
    if kind == "object":
        if type(value) is not dict:
            return f"{path}: object required"
        extra = set(value) - set(schema["properties"])
        if extra:
            return f"{path}: undeclared fields {sorted(extra)}"
        for key in schema["required"]:
            if key not in value:
                return f"{path}.{key}: required"
        for key, item in value.items():
            error = conforms(schema["properties"][key], item, f"{path}.{key}")
            if error:
                return error
        return None
    if kind == "array":
        if type(value) is not list:
            return f"{path}: array required"
        if not schema["minItems"] <= len(value) <= schema["maxItems"]:
            return f"{path}: between {schema['minItems']} and {schema['maxItems']} items required"
        for index, item in enumerate(value):
            error = conforms(schema["items"], item, f"{path}[{index}]")
            if error:
                return error
        return None
    if kind == "string":
        if type(value) is not str:
            return f"{path}: string required"
        if "enum" in schema and value not in schema["enum"]:
            return f"{path}: one of {schema['enum']} required"
        if not schema["minLength"] <= len(value) <= schema["maxLength"]:
            return f"{path}: length between {schema['minLength']} and {schema['maxLength']} required"
        return None
    if kind == "integer":
        if type(value) is not int:
            return f"{path}: exact integer required"
    elif kind == "number":
        if type(value) not in (int, float) or not math.isfinite(value):
            return f"{path}: finite number required"
    elif kind == "boolean":
        return None if type(value) is bool else f"{path}: boolean required"
    else:
        return None if value is None else f"{path}: null required"
    if "minimum" in schema and value < schema["minimum"]:
        return f"{path}: minimum {schema['minimum']}"
    if "maximum" in schema and value > schema["maximum"]:
        return f"{path}: maximum {schema['maximum']}"
    return None


# ---------------------------------------------------------------- declarations

def model_config(value):
    _fields(value, "model", ("provider", "model", "max_new_tokens", "prompt_token_bound",
                             "prompt_overhead_tokens"), ("temperature", "stop_sequences"))
    if value["provider"] not in PROVIDERS:
        raise ContractError("provider must be one of " + ", ".join(PROVIDERS))
    out = {"provider": value["provider"], "model": _text(value["model"], "model", 128),
           "max_new_tokens": _count(value["max_new_tokens"], "max_new_tokens", 1, 1 << 20),
           "prompt_token_bound": _count(value["prompt_token_bound"], "prompt_token_bound", 1, 1 << 24),
           "prompt_overhead_tokens": _count(value["prompt_overhead_tokens"], "prompt_overhead_tokens", 0, 1 << 16)}
    if "temperature" in value:
        if not 0 <= _number(value["temperature"], "temperature") <= 1:
            raise ContractError("temperature must be in [0, 1]")
        out["temperature"] = value["temperature"]
    if "stop_sequences" in value:
        stops = value["stop_sequences"]
        if type(stops) is not list or len(stops) > 4 or any(type(s) is not str or not 0 < len(s) <= 64 for s in stops):
            raise ContractError("stop_sequences must be at most four short strings")
        out["stop_sequences"] = list(stops)
    return out


def capacity_spec(value):
    """The DECLARED workforce: primitive facts only, never derived quantities.

    Each worker declares one primitive, its ``cost``. ``cheapest_cost`` and
    ``cheaper_workers`` are DERIVED by the policy plane from this frozen model and
    the eligible set of the task actually under consideration, so two workers can
    never contradict each other about who is cheapest, and nothing is ever inferred
    from who happens to be idle or online.

    ``service_time`` is one SHARED scalar, not a per-worker field. The incumbent L2
    mechanism takes a single service time, so declaring one per worker would force an
    unjustified aggregation choice (whose time? the mean? the harmonic mean?) and
    would quietly introduce a new scheduling model under the old name. Heterogeneous
    service rates need their own mechanism and their own validation; until that
    exists, the declaration cannot express them.
    """
    _fields(value, "capacity", ("workers", "latency_cost", "service_time"))
    workers = value["workers"]
    if type(workers) is not dict or not workers or len(workers) > 64:
        raise ContractError("capacity needs a bounded nonempty worker map")
    out = {}
    for name, worker in workers.items():
        _name(name, "capacity worker")
        _fields(worker, "worker capacity", ("cost",))
        cost = float(_number(worker["cost"], "worker cost"))
        if cost < 0:
            raise ContractError("a worker needs a nonnegative cost")
        out[name] = {"cost": cost}
    latency = float(_number(value["latency_cost"], "latency_cost"))
    if latency < 0:
        raise ContractError("latency_cost must be nonnegative")
    service = float(_number(value["service_time"], "service_time"))
    if service <= 0:
        raise ContractError("service_time must be positive")
    return {"workers": out, "latency_cost": latency, "service_time": service}


def worker_order(spec):
    """The serial host's worker-enumeration order: the order agents are DECLARED in.

    This is part of workload identity, not an incidental detail. Which worker is
    offered a shared task first decides who claims it under a policy that some
    workers defer under, so a silent reordering would change an experimental
    condition without changing the arm. ``agents`` is a JSON list, so its order is
    already inside the spec digest: canonicalization sorts object keys and never
    reorders a list. Reading it through this one function keeps that guarantee in a
    single named place instead of relying on every caller to iterate in order.
    """
    return [agent["id"] for agent in spec["agents"]]


def agent_spec(value):
    _fields(value, "agent", ("id", "model", "capabilities"))
    if value["id"] == HOST_AGENT:
        raise ContractError("the host identity is reserved")
    capabilities = _fields(value["capabilities"], "capabilities", ("tools",))
    return {"id": _name(value["id"], "agent id"), "model": model_config(value["model"]),
            "capabilities": {"tools": _names(capabilities["tools"], "capability tools")}}


# The commitment slot is deliberately absent: orchestration has no candidate
# arbitration locus yet, so declaring a commitment rule would be decorative. The
# capacity model is workflow-level (see capacity_spec), so the allocation block
# carries only the rule and the parameters of the rule itself.
POLICY_SLOTS = {
    "allocation": {"fifo": ((), ()),
                   "threshold": ((), ()),
                   "response": (("exponent",), ("seed",))},
    "lease": {"fixed": ((), ("seconds",)),
              "evaporation": (("stage_durations", "p_fail", "per_tick_cost", "false_expiry_cost"), ())},
}
UNIT_FIELDS = ("p_fail",)
# cheaper_workers is DERIVED by the policy plane from the frozen capacity model and a
# task's eligible set; it is not a declarable policy field and never appears in a spec.
COUNT_FIELDS = ("exponent",)


def _policy(slot, value):
    """One declared policy: its kind plus exactly that kind's parameters."""
    kinds = POLICY_SLOTS[slot]
    if type(value) is not dict or value.get("kind") not in kinds:
        raise ContractError(slot + " kind must be one of " + ", ".join(sorted(kinds)))
    required, optional = kinds[value["kind"]]
    _fields(value, slot, ("kind",) + required, optional)
    out = {"kind": value["kind"]}
    for name, item in value.items():
        if name == "kind":
            continue
        if name == "seed":
            out[name] = _text(item, "seed", 64)
        elif name in COUNT_FIELDS:
            out[name] = _count(item, name, 1 if name == "exponent" else 0, 1 << 20)
        elif name in ("stage_durations",):
            if type(item) is not list or not item or len(item) > 1024:
                raise ContractError(name + " must be a bounded nonempty list")
            out[name] = [float(_number(entry, name)) for entry in item]
            if any(entry < 0 for entry in out[name]):
                raise ContractError(name + " must be nonnegative")
        else:
            out[name] = float(_number(item, name))
            if out[name] < 0 or (name == "service_time" and out[name] <= 0):
                raise ContractError(name + " must be nonnegative")
        if name in UNIT_FIELDS and not 0 <= out[name] <= 1:
            raise ContractError(name + " must be in [0,1]")
    if value["kind"] == "evaporation" and not any(entry > 0 for entry in out["stage_durations"]):
        raise ContractError("stage_durations needs at least one positive lead time")
    if value["kind"] == "fixed" and out.get("seconds", 1.) <= 0:
        raise ContractError("a fixed lease needs a positive duration")
    return out


def policies_spec(value):
    """The declared colony policy plane; an omitted slot keeps the baseline."""
    _fields(value, "policies", (), tuple(POLICY_SLOTS))
    return {slot: _policy(slot, value[slot]) for slot in POLICY_SLOTS if slot in value}


def task_limits(value):
    _fields(value, "limits", ("model_steps", "tool_calls", "rejections", "calls", "tokens"))
    return {"model_steps": _count(value["model_steps"], "model_steps", 1, 1024),
            "tool_calls": _count(value["tool_calls"], "tool_calls", 0, 1024),
            "rejections": _count(value["rejections"], "rejections", 0, 1024),
            "calls": _count(value["calls"], "calls", 1),
            "tokens": _count(value["tokens"], "tokens", 0)}


def decomposition_config(value):
    _fields(value, "decomposition", ("max_children", "child_output_schema", "join_reserve"))
    join = _fields(value["join_reserve"], "join_reserve", ("model_steps", "calls", "tokens"))
    return {"max_children": _count(value["max_children"], "max_children", 1, 64),
            "child_output_schema": validate_schema(value["child_output_schema"]),
            "join_reserve": {"model_steps": _count(join["model_steps"], "join model_steps", 1, 1024),
                             "calls": _count(join["calls"], "join calls", 1),
                             "tokens": _count(join["tokens"], "join tokens", 0)}}


def rule_spec(value):
    """The host acceptance rule: which artifacts it reads and which checker binds them.

    This is a verification rule, not a commitment rule. It decides whether the
    declared finite checker passed on the exact candidate digest; no commitment
    policy may overturn that verdict.
    """
    _fields(value, "rule", ("type", "candidate", "review", "checker"))
    if value["type"] not in RULES:
        raise ContractError("rule type must be one of " + ", ".join(RULES))
    return {"type": value["type"], "candidate": _name(value["candidate"], "rule candidate"),
            "review": _name(value["review"], "rule review"), "checker": _name(value["checker"], "rule checker")}


def eligible_agents(task):
    """The agents a task declares as legal executors, in either schema version."""
    return list(task["agents"]) if "agents" in task else [task["agent"]]


def task_spec(value, spec_format=SPEC_FORMAT):
    if type(value) is not dict or value.get("kind") not in TASK_KINDS:
        raise ContractError("task kind must be model or host")
    legacy = spec_format == LEGACY_SPEC_FORMAT
    if value["kind"] == "host":
        # v1 records keep `agent` so their digest is untouched; v2 canonicalizes to the
        # list. `agent` on input is accepted either way and normalized for v2 output.
        _fields(value, "host task", ("id", "kind", "dependencies", "reads", "rule"),
                ("version",) + (("agent",) if legacy else ("agent", "agents")))
        if legacy and "agent" not in value:
            raise ContractError("a v1 host task names its agent")
        if not legacy and ("agent" in value) == ("agents" in value):
            raise ContractError("a host task names the host identity once")
        named = [value["agent"]] if "agent" in value else value["agents"]
        if named != [HOST_AGENT]:
            raise ContractError("host tasks run as the host identity")
        out = {"id": _name(value["id"], "task id"), "version": _count(value.get("version", 1), "version", 1),
               "kind": "host", **({"agent": HOST_AGENT} if legacy else {"agents": [HOST_AGENT]}),
               "dependencies": _names(value["dependencies"], "dependencies"),
               "reads": _names(value["reads"], "reads"), "rule": rule_spec(value["rule"])}
    else:
        _fields(value, "model task", ("id", "kind", "instructions", "dependencies", "reads", "tools",
                                      "output_schema", "limits"),
                ("version", "decomposition", "agent") + (() if legacy else ("agents",)))
        # A v1 task has exactly one executor and keeps that shape. A v2 task declares
        # the agents ELIGIBLE to execute it; `agent` is accepted and normalized to the
        # list, so the durable schema never holds both shapes at once.
        if legacy and "agent" not in value:
            raise ContractError("a v1 model task names its agent")
        if not legacy and ("agent" in value) == ("agents" in value):
            raise ContractError("a model task declares either one agent or an eligible agents list")
        eligible = _names([value["agent"]] if "agent" in value else value["agents"], "task agents")
        if not eligible:
            raise ContractError("a model task needs at least one eligible agent")
        out = {"id": _name(value["id"], "task id"), "version": _count(value.get("version", 1), "version", 1),
               "kind": "model", **({"agent": eligible[0]} if legacy else {"agents": eligible}),
               "instructions": _text(value["instructions"], "instructions", MAX_INSTRUCTIONS),
               "dependencies": _names(value["dependencies"], "dependencies"),
               "reads": _names(value["reads"], "reads"), "tools": _names(value["tools"], "tools"),
               "output_schema": validate_schema(value["output_schema"]),
               "limits": task_limits(value["limits"]),
               "decomposition": None if value.get("decomposition") is None else decomposition_config(value["decomposition"])}
        if set(out["tools"]) & set(RESERVED_TOOLS):
            raise ContractError("task tools cannot name a reserved action")
    if not set(out["reads"]) <= set(out["dependencies"]):
        raise ContractError("a task may read only artifacts of its dependencies")
    return out


def tool_spec(value):
    _fields(value, "tool", ("name", "version"), ("config",))
    name = _name(value["name"], "tool name")
    if name in RESERVED_TOOLS:
        raise ContractError("tool name is a reserved action")
    config = finite_json(value.get("config", {}))
    if type(config) is not dict or len(wire(config).encode()) > 2048:
        raise ContractError("tool config must be a small object")
    return {"name": name, "version": _text(value["version"], "tool version", 64), "config": config}


def fixture_spec(value):
    """A declared fixture: a bounded relative path with the content digest and size.

    The digest is the host's declaration of the file it authorized, checked again at
    every read; it is not a claim that the content is correct or meaningful.
    """
    _fields(value, "fixture", ("path", "sha256", "bytes"))
    path = _text(value["path"], "fixture path", 512)
    parts = path.split("/")
    if path.startswith("/") or "\\" in path or "" in parts or ".." in parts or "." in parts:
        raise ContractError("fixture path must be a plain relative POSIX path")
    fingerprint = value["sha256"]
    if (type(fingerprint) is not str or len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)):
        raise ContractError("fixture sha256 must be 64 lowercase hex characters")
    return {"path": path, "sha256": fingerprint, "bytes": _count(value["bytes"], "fixture bytes", 0, 1 << 20)}


def run_limits(value):
    _fields(value, "limits", ("max_calls", "token_cap", "context_bytes", "artifact_bytes", "max_work_items",
                              "max_children", "max_depth", "max_platform_operations"))
    return {"max_calls": _count(value["max_calls"], "max_calls", 1), "token_cap": _count(value["token_cap"], "token_cap", 0),
            "context_bytes": _count(value["context_bytes"], "context_bytes", 1),
            "artifact_bytes": _count(value["artifact_bytes"], "artifact_bytes", 1),
            "max_work_items": _count(value["max_work_items"], "max_work_items", 1),
            "max_children": _count(value["max_children"], "max_children", 1),
            "max_depth": _count(value["max_depth"], "max_depth", 1),
            "max_platform_operations": _count(value["max_platform_operations"], "max_platform_operations", 1)}


def _acyclic(graph):
    pending = {key: set(deps) for key, deps in graph.items()}
    if any(deps - set(graph) for deps in pending.values()):
        raise ContractError("dependency on an undeclared task")
    while pending:
        leaves = {key for key, deps in pending.items() if not deps}
        if not leaves:
            raise ContractError("cyclic task dependencies")
        pending = {key: deps - leaves for key, deps in pending.items() if key not in leaves}


def workflow_spec(value):
    """Validate a workflow declaration; the returned record is canonical and self-consistent."""
    _fields(value, "workflow", ("format", "run_id", "agents", "tools", "fixtures", "tasks", "limits"),
            ("policies", "capacity"))
    if value["format"] not in SPEC_FORMATS:
        raise ContractError("unsupported workflow format")
    spec_format = value["format"]
    if spec_format == LEGACY_SPEC_FORMAT and value.get("capacity") is not None:
        raise ContractError("a v1 workflow declares no capacity model")
    agents = [agent_spec(item) for item in (value["agents"] if type(value["agents"]) is list else [None])]
    tools = [tool_spec(item) for item in (value["tools"] if type(value["tools"]) is list else [None])]
    tasks = [task_spec(item, spec_format) for item in (value["tasks"] if type(value["tasks"]) is list else [None])]
    if type(value["fixtures"]) is not dict or len(value["fixtures"]) > 64:
        raise ContractError("fixtures must be a small name-to-declaration map")
    fixtures = {_name(name, "fixture name"): fixture_spec(item) for name, item in value["fixtures"].items()}
    limits = run_limits(value["limits"])
    if len({a["id"] for a in agents}) != len(agents) or len({t["name"] for t in tools}) != len(tools):
        raise ContractError("agent ids and tool names must be unique")
    ids = [task["id"] for task in tasks]
    if not tasks or len(set(ids)) != len(ids) or len(tasks) > limits["max_work_items"]:
        raise ContractError("tasks must be nonempty, unique and within max_work_items")
    _acyclic({task["id"]: task["dependencies"] for task in tasks})
    by_id = {task["id"]: task for task in tasks}
    agent_tools = {agent["id"]: set(agent["capabilities"]["tools"]) for agent in agents}
    declared = {tool["name"] for tool in tools}
    for agent in agents:
        if not agent_tools[agent["id"]] <= declared:
            raise ContractError("agent capability names an undeclared tool")
    for tool in tools:
        if "fixture" in tool["config"] and tool["config"]["fixture"] not in fixtures:
            raise ContractError("tool config names an undeclared fixture")
    for task in tasks:
        if task["kind"] == "model":
            names = eligible_agents(task)
            if not set(names) <= set(agent_tools):
                raise ContractError("task names an agent that is not declared")
            shared = set.intersection(*(agent_tools[name] for name in names))
            if not set(task["tools"]) <= shared:
                raise ContractError("task tools exceed the capability every eligible agent shares")
            if task["limits"]["calls"] > limits["max_calls"] or task["limits"]["tokens"] > limits["token_cap"]:
                raise ContractError("task budget exceeds run limits")
            if task["decomposition"] and task["decomposition"]["max_children"] > limits["max_children"]:
                raise ContractError("decomposition exceeds max_children")
        else:
            rule = task["rule"]
            if rule["candidate"] == rule["review"] or not {rule["candidate"], rule["review"]} <= set(task["reads"]):
                raise ContractError("rule inputs must be distinct readable dependencies")
            review = by_id[rule["review"]]
            if review["kind"] != "model" or rule["checker"] not in review["tools"]:
                raise ContractError("the rule's checker must be a tool of the review task")
    declared = policies_spec(value.get("policies") or {})
    capacity = None if value.get("capacity") is None else capacity_spec(value["capacity"])
    if (declared.get("allocation") or {}).get("kind") in ("threshold", "response"):
        if capacity is None:
            raise ContractError("a threshold allocation needs a declared capacity model")
        missing = {agent["id"] for agent in agents} - set(capacity["workers"])
        if missing:
            raise ContractError("the capacity model omits " + ", ".join(sorted(missing)))
        # Degeneracy is judged at the DECISION LOCUS, which is a task's eligible set.
        # A cost spread across the workforce is worth nothing if no task lets two
        # differently priced workers compete for it: the policy would then be FIFO in
        # disguise, so refuse rather than degenerate silently.
        costs = {name: worker["cost"] for name, worker in capacity["workers"].items()}
        if not any(len({costs[name] for name in eligible_agents(task)}) > 1
                   for task in tasks if task["kind"] == "model"):
            raise ContractError("a threshold allocation needs at least one task whose eligible "
                                "agents differ in declared cost; otherwise declare the fifo allocation")
    return {"format": spec_format, "run_id": _text(value["run_id"], "run_id", 128), "agents": agents,
            "tools": tools, "fixtures": fixtures, "tasks": tasks, "limits": limits,
            "policies": declared, **({} if capacity is None else {"capacity": capacity})}


# ---------------------------------------------------------------- proposals

CHILD_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def children_schema(config, parent_tools, sibling_bound):
    """The propose_children input schema for a task in decomposition mode.

    Every field is a NARROWING REQUEST checked against the parent at admission, not
    a grant: the host refuses tools outside the parent's, reads outside the parent's
    reads plus siblings, step/tool/rejection limits above the parent's remaining, and
    budgets that would leave less than the declared join reserve.
    """
    child = {"type": "object", "additionalProperties": False,
             "required": ["name", "instructions", "tools", "reads", "dependencies", "limits"],
             "properties": {
                 "name": {"type": "string", "maxLength": 32, "minLength": 1},
                 "instructions": {"type": "string", "maxLength": 2048, "minLength": 1},
                 "tools": {"type": "array", "items": {"type": "string", "enum": list(parent_tools) or ["none"]},
                           "maxItems": max(len(parent_tools), 1)},
                 "reads": {"type": "array", "items": {"type": "string", "maxLength": 32}, "maxItems": sibling_bound},
                 "dependencies": {"type": "array", "items": {"type": "string", "maxLength": 32}, "maxItems": sibling_bound},
                 "limits": {"type": "object", "additionalProperties": False,
                            "required": ["model_steps", "tool_calls", "rejections", "calls", "tokens"],
                            "properties": {name: {"type": "integer", "minimum": 0, "maximum": 1 << 30}
                                           for name in ("model_steps", "tool_calls", "rejections", "calls", "tokens")}}}}
    return validate_schema({"type": "object", "additionalProperties": False, "required": ["children"],
                            "properties": {"children": {"type": "array", "items": child, "minItems": 1,
                                                        "maxItems": config["max_children"]}}})


ABSTAIN_SCHEMA = validate_schema({"type": "object", "additionalProperties": False, "required": ["reason"],
                                  "properties": {"reason": {"type": "string", "maxLength": MAX_REASON, "minLength": 1}}})


def parse_proposal(response, *, tools, output_schema, decomposition=None):
    """Parse one settled model receipt artifact into a proposal, or raise ContractError.

    ``tools`` maps permitted tool names to their argument schemas. Exactly one
    ``tool_use`` block is accepted; its name selects the proposal kind and its input
    is checked against the matching schema. Text blocks are ignored. A truncated
    response, no action, several actions, an unknown or unpermitted name, or
    nonconforming input are validation failures with a reason the host may show to
    the model on its next step; none of them executes anything.
    """
    if type(response) is not dict or type(response.get("content")) is not list:
        raise ContractError("response lacks content blocks")
    if response.get("stop_reason") == "max_tokens":
        raise ContractError("response truncated at max_tokens; no action accepted")
    uses = [block for block in response["content"] if type(block) is dict and block.get("type") == "tool_use"]
    if len(uses) != 1:
        raise ContractError("exactly one tool_use action required, got %d" % len(uses))
    use = uses[0]
    name, arguments, use_id = use.get("name"), use.get("input"), use.get("id")
    if type(name) is not str or type(arguments) is not dict or type(use_id) is not str or not use_id:
        raise ContractError("tool_use needs a string name, an object input and an id")
    arguments = finite_json(arguments)
    if name == "submit_output":
        error = conforms(output_schema, arguments)
        if error:
            raise ContractError("submit_output does not conform to the output schema: " + error)
        proposal = {"kind": "submit", "output": arguments}
    elif name == "abstain":
        error = conforms(ABSTAIN_SCHEMA, arguments)
        if error:
            raise ContractError("abstain does not conform: " + error)
        proposal = {"kind": "abstain", "reason": arguments["reason"]}
    elif name == "propose_children":
        if decomposition is None:
            raise ContractError("propose_children is not available for this task")
        error = conforms(decomposition, arguments)
        if error:
            raise ContractError("propose_children does not conform: " + error)
        proposal = {"kind": "decompose", "children": arguments["children"]}
    elif name in tools:
        error = conforms(tools[name], arguments)
        if error:
            raise ContractError(f"arguments for {name} do not conform: " + error)
        proposal = {"kind": "tool", "tool": name, "arguments": arguments}
    else:
        raise ContractError(f"action {name!r} is not permitted for this task")
    proposal["tool_use_id"] = use_id
    return proposal


def proposal_digest(proposal):
    return digest(proposal)


# ---------------------------------------------------------------- outcomes

def outcome(status, reason, tasks, metrics):
    if status not in OUTCOMES:
        raise ContractError("unknown outcome status")
    return {"format": OUTCOME_FORMAT, "status": status, "reason": _text(reason, "reason", MAX_REASON),
            "tasks": finite_json(tasks), "metrics": finite_json(metrics)}
