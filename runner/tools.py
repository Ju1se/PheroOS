"""Allowlisted read-only tools: schema-checked arguments, byte-bounded outputs.

A registered tool is a pure function of its validated arguments, the bytes of a
declared fixture and the artifacts the calling task may read through the supplied
resolver. There is no session, database handle, credential, clock, randomness,
network or arbitrary path in this module, and nothing here grants a permission:
registration records what a tool accepts, and a name inside a tool argument is
data until the host resolves it against a declaration. A fixture digest match
says the bytes are the ones the host declared, not that their content is correct;
a checker's ``pass`` says the candidate satisfied that finite comparison, not that
it is semantically right.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import os
import stat

from . import contracts

DEFAULT_OUTPUT_BYTES = 8192
MAX_MISMATCHES = 8
MISMATCH_BYTES = 96


class ToolError(ValueError):
    """A declaration, argument set, fixture read or tool output failed validation.

    Every failure that crosses this module is a ToolError; it is a data error and
    never an instruction to the host or to a model.
    """


def _text(value, label, maximum):
    if type(value) is not str or not value.strip() or len(value.encode()) > maximum:
        raise ToolError(f"{label} must be nonempty text of at most {maximum} bytes")
    return value


def _copy(value):
    return json.loads(contracts.wire(value))


def _short(text):
    return text if len(text) <= MISMATCH_BYTES else text[:MISMATCH_BYTES - 3] + "..."


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ToolError("duplicate JSON field")
        result[key] = value
    return result


def _parse(raw):
    """Parse strict JSON: duplicate object keys and NaN/Infinity constants are refused."""
    try:
        return json.loads(raw, object_pairs_hook=_unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(ToolError("nonfinite JSON constant")))
    except ToolError:
        raise
    except ValueError as error:
        raise ToolError(f"fixture content is not strict JSON: {error}") from error


def _open_within(root, relative):
    """Open a relative path under root without following a symlink at any component."""
    parts = relative.split("/")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            nested = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = nested
        return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)


def _read_bounded(descriptor, limit):
    chunks, total = [], 0
    while total < limit:
        chunk = os.read(descriptor, limit - total)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


class FixtureStore:
    """Declared fixture files, re-validated on construction and digest-checked at every read.

    Reads are confined to the declared relative paths under ``root``: no symlink is
    followed at any path component, so nothing outside the declared set is reachable,
    and a file whose size or digest differs from its declaration is refused rather
    than returned. The store never writes, caches or watches a file, and says nothing
    about what the bytes mean.
    """

    def __init__(self, root, fixtures):
        try:
            self.root = Path(root)
        except TypeError as error:
            raise ToolError("fixture root must be a filesystem path") from error
        if type(fixtures) is not dict:
            raise ToolError("fixtures must be a name-to-declaration map")
        declarations = {}
        for name, entry in fixtures.items():
            if type(name) is not str or not contracts.NAME.match(name):
                raise ToolError(f"fixture name must match {contracts.NAME.pattern}")
            try:
                declarations[name] = contracts.fixture_spec(entry)
            except contracts.ContractError as error:
                raise ToolError(f"fixture {name!r} declaration is invalid: {error}") from error
        self._fixtures = declarations

    def names(self):
        return sorted(self._fixtures)

    def declaration(self, name):
        if type(name) is not str or name not in self._fixtures:
            raise ToolError(f"fixture {name!r} is not declared")
        return dict(self._fixtures[name])

    def read(self, name):
        """Return the declared bytes of one fixture, or raise ToolError."""
        entry = self.declaration(name)
        try:
            descriptor = _open_within(self.root, entry["path"])
        except OSError as error:
            raise ToolError(f"fixture {name!r} cannot be opened: {error.strerror}") from error
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ToolError(f"fixture {name!r} is not a regular file")
            raw = _read_bounded(descriptor, entry["bytes"] + 1)
        except OSError as error:
            raise ToolError(f"fixture {name!r} cannot be read: {error.strerror}") from error
        finally:
            os.close(descriptor)
        if len(raw) != entry["bytes"]:
            raise ToolError(f"fixture {name!r} is {len(raw)} bytes where {entry['bytes']} were declared")
        if sha256(raw).hexdigest() != entry["sha256"]:
            raise ToolError(f"fixture {name!r} content does not match its declared sha256")
        return raw


class ToolRegistry:
    """Named read-only tools with validated argument schemas and bounded outputs.

    The registry decides nothing about who may call a tool: the caller passes only
    names a task declaration already allows, and a registered tool receives validated
    arguments plus the resolver the host chose for that task, never a session.
    """

    def __init__(self):
        self._tools = {}

    def register(self, name, *, version, description, schema, execute, output_bytes=DEFAULT_OUTPUT_BYTES):
        if type(name) is not str or not contracts.NAME.match(name):
            raise ToolError(f"tool name must match {contracts.NAME.pattern}")
        if name in contracts.RESERVED_TOOLS:
            raise ToolError(f"tool name {name!r} is a reserved action")
        if name in self._tools:
            raise ToolError(f"tool {name!r} is already registered")
        if not callable(execute):
            raise ToolError("execute must be callable")
        if type(output_bytes) is not int or output_bytes < 1:
            raise ToolError("output_bytes must be an exact integer >= 1")
        try:
            validated = contracts.validate_schema(schema)
        except contracts.ContractError as error:
            raise ToolError(f"tool {name!r} has an invalid input schema: {error}") from error
        if validated["type"] != "object":
            raise ToolError("a tool input schema must be an object schema")
        self._tools[name] = {"version": _text(version, "tool version", 64),
                             "description": _text(description, "tool description", 1024),
                             "schema": validated, "execute": execute, "output_bytes": output_bytes}

    def _entry(self, name):
        if type(name) is not str or name not in self._tools:
            raise ToolError(f"tool {name!r} is not registered")
        return self._tools[name]

    def names(self):
        return sorted(self._tools)

    def version(self, name):
        return self._entry(name)["version"]

    def schema(self, name):
        return _copy(self._entry(name)["schema"])

    def output_bytes(self, name):
        return self._entry(name)["output_bytes"]

    def declaration(self, name):
        """Return the provider-visible entry for one tool; the caller may not alter the registry through it."""
        entry = self._entry(name)
        return {"name": name, "description": entry["description"], "input_schema": _copy(entry["schema"])}

    def declarations(self, names):
        if type(names) not in (list, tuple):
            raise ToolError("names must be a list of registered tool names")
        return [self.declaration(name) for name in names]

    def execute(self, name, arguments, resolver):
        """Validate arguments against the declared schema, then run the tool and bound its output.

        A nonconforming argument set is refused before the tool runs. The returned
        value is a finite-JSON copy; it is evidence, not a decision.
        """
        entry = self._entry(name)
        if type(arguments) is not dict:
            raise ToolError(f"arguments for {name} must be an object")
        try:
            checked = contracts.finite_json(arguments)
        except contracts.ContractError as error:
            raise ToolError(f"arguments for {name} are not finite JSON: {error}") from error
        error = contracts.conforms(entry["schema"], checked)
        if error:
            raise ToolError(f"arguments for {name} do not conform: {error}")
        output = entry["execute"](checked, resolver)
        if type(output) is not dict:
            raise ToolError(f"tool {name} must return an object")
        try:
            finite = contracts.finite_json(output)
        except contracts.ContractError as failure:
            raise ToolError(f"tool {name} returned a value that is not finite JSON: {failure}") from failure
        if len(contracts.wire(finite).encode()) > entry["output_bytes"]:
            raise ToolError(f"tool {name} output exceeds {entry['output_bytes']} bytes")
        return finite


# ---------------------------------------------------------------- built-in tools

def fixture_read_schema(names):
    """The input schema of a ``fixture.read`` scoped to exactly the fixtures it may read."""
    return {"type": "object", "additionalProperties": False, "required": ["name"],
            "properties": {"name": {"type": "string", "enum": sorted(names),
                                    "description": "one of the fixtures this tool is scoped to"}}}

CANDIDATE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["candidate_ref"],
                    "properties": {"candidate_ref": {"type": "string", "maxLength": 128, "minLength": 1}}}


def _resolve(resolver, ref):
    read_artifact = getattr(resolver, "read_artifact", None)
    if not callable(read_artifact):
        raise ToolError("a resolver with read_artifact is required")
    artifact = read_artifact(ref)
    if artifact is None:
        raise ToolError("candidate not visible")
    if type(artifact) is not dict or "value" not in artifact:
        raise ToolError("resolver returned a malformed artifact")
    return artifact


def _artifact_digest(artifact):
    try:
        return contracts.digest(artifact["value"])
    except (TypeError, ValueError) as error:
        raise ToolError("candidate artifact value is not finite JSON") from error


def _expected_totals(content, fixture):
    """Sum the declared orders per category; a malformed declared source is an error, not a verdict."""
    if type(content) is not dict or set(content) != {"orders"} or type(content["orders"]) is not list:
        raise ToolError(f"fixture {fixture!r} must hold an orders array")
    totals = {}
    for order in content["orders"]:
        if (type(order) is not dict or set(order) != {"id", "category", "amount_cents"}
                or type(order["id"]) is not str or type(order["category"]) is not str
                or type(order["amount_cents"]) is not int or order["amount_cents"] < 0):
            raise ToolError(f"fixture {fixture!r} holds a malformed order row")
        totals[order["category"]] = totals.get(order["category"], 0) + order["amount_cents"]
    return sorted(totals.items())


def _totals_problems(value, expected):
    """Every structural difference between a candidate and the expected totals, as short strings."""
    if type(value) is not dict:
        return [_short("candidate is not an object")]
    problems = []
    missing = sorted({"totals", "total_cents"} - set(value))
    if missing:
        problems.append(_short("missing fields " + ", ".join(missing)))
    extra = sorted(set(value) - {"totals", "total_cents"})
    if extra:
        problems.append(_short("undeclared fields " + ", ".join(extra)))
    expected_totals = dict(expected)
    if "totals" in value:
        problems.extend(_row_problems(value["totals"], expected_totals))
    expected_total = sum(cents for _, cents in expected)
    if "total_cents" in value and (type(value["total_cents"]) is not int
                                   or value["total_cents"] != expected_total):
        problems.append(_short(f"total_cents: expected {expected_total}, got {value['total_cents']!r}"))
    return problems


def _row_problems(rows, expected_totals):
    if type(rows) is not list:
        return [_short("totals is not an array")]
    problems, pairs = [], []
    for index, row in enumerate(rows):
        if (type(row) is not dict or set(row) != {"category", "cents"}
                or type(row["category"]) is not str or type(row["cents"]) is not int):
            problems.append(_short(f"totals[{index}] is not a category/cents pair"))
            continue
        pairs.append((row["category"], row["cents"]))
    categories = [category for category, _ in pairs]
    if categories != sorted(categories):
        problems.append(_short("totals is not sorted by category"))
    duplicates = sorted({name for name in categories if categories.count(name) > 1})
    if duplicates:
        problems.append(_short("duplicate category " + ", ".join(duplicates)))
    actual = dict(pairs)
    for category in sorted(set(expected_totals) - set(actual)):
        problems.append(_short(f"missing category {category}"))
    for category in sorted(set(actual) - set(expected_totals)):
        problems.append(_short(f"unexpected category {category}"))
    for category in sorted(set(actual) & set(expected_totals)):
        if actual[category] != expected_totals[category]:
            problems.append(_short(f"{category}: expected {expected_totals[category]} cents,"
                                   f" got {actual[category]}"))
    return problems


def _fixture_read(store, allowed):
    def execute(arguments, resolver):
        if arguments["name"] not in allowed:
            raise ToolError(f"fixture {arguments['name']!r} is outside this tool's scope")
        raw = store.read(arguments["name"])
        return {"name": arguments["name"], "bytes": len(raw),
                "digest": sha256(raw).hexdigest(), "content": _parse(raw)}
    return execute


def _category_totals(store, fixture):
    def execute(arguments, resolver):
        artifact = _resolve(resolver, arguments["candidate_ref"])
        expected = _expected_totals(_parse(store.read(fixture)), fixture)
        problems = _totals_problems(artifact["value"], expected)
        return {"candidate_ref": arguments["candidate_ref"], "candidate_digest": _artifact_digest(artifact),
                "pass": not problems,
                "detail": {"expected_total_cents": sum(cents for _, cents in expected),
                           "mismatches": problems[:MAX_MISMATCHES]}}
    return execute


def _expected_json(store, fixture):
    def execute(arguments, resolver):
        artifact = _resolve(resolver, arguments["candidate_ref"])
        expected = _parse(store.read(fixture))
        candidate_digest = _artifact_digest(artifact)
        return {"candidate_ref": arguments["candidate_ref"], "candidate_digest": candidate_digest,
                "pass": contracts.wire(artifact["value"]) == contracts.wire(expected),
                "detail": {"expected_digest": contracts.digest(expected)}}
    return execute


def _fixture_name(config, name, store):
    if type(config) is not dict or set(config) != {"fixture"}:
        raise ToolError(f"tool {name!r} requires a config naming exactly one fixture")
    if config["fixture"] not in store.names():
        raise ToolError(f"tool {name!r} names an undeclared fixture")
    return config["fixture"]


def _fixture_names(config, name, store):
    """A reader is scoped to an explicit fixture list; an unscoped reader is refused.

    Without a scope every holder of this tool could read every declared fixture,
    including one that another task's checker uses as its answer key.
    """
    if type(config) is not dict or set(config) != {"fixtures"}:
        raise ToolError(f"tool {name!r} requires a config naming the fixtures it may read")
    names = config["fixtures"]
    if type(names) is not list or not names or len(set(names)) != len(names):
        raise ToolError(f"tool {name!r} needs a nonempty list of distinct fixture names")
    if not set(names) <= set(store.names()):
        raise ToolError(f"tool {name!r} names an undeclared fixture")
    return sorted(names)


def _build_fixture_read(registry, store, entry):
    allowed = _fixture_names(entry["config"], entry["name"], store)
    registry.register(entry["name"], version=entry["version"], schema=fixture_read_schema(allowed),
                      description="Return one of this tool's declared fixture files as strict JSON with its size"
                                  " and digest; the digest attests the declared bytes, not their correctness.",
                      execute=_fixture_read(store, set(allowed)))


def _build_category_totals(registry, store, entry):
    fixture = _fixture_name(entry["config"], entry["name"], store)
    registry.register(entry["name"], version=entry["version"], schema=CANDIDATE_SCHEMA,
                      description="Compare a readable candidate artifact with the per-category order totals of a"
                                  " declared fixture; a pass is that finite comparison, not a claim of correctness.",
                      execute=_category_totals(store, fixture))


def _build_expected_json(registry, store, entry):
    fixture = _fixture_name(entry["config"], entry["name"], store)
    registry.register(entry["name"], version=entry["version"], schema=CANDIDATE_SCHEMA,
                      description="Compare a readable candidate artifact with the canonical JSON of a declared"
                                  " fixture; a pass means the two serializations are identical, nothing more.",
                      execute=_expected_json(store, fixture))


BUILTINS = {"fixture.read": _build_fixture_read,
            "checker.category_totals": _build_category_totals,
            "checker.expected_json": _build_expected_json}


def build_registry(spec, spec_dir):
    """Register the built-in tool named by every entry of a canonical workflow spec.

    Only the fixtures and the tools of the spec are consulted; agents, tasks and
    limits belong to the runtime, and no fixture file is opened here. Registration
    authorizes nothing: a task may still call only the tools its own declaration lists.
    """
    if type(spec) is not dict or type(spec.get("tools")) is not list:
        raise ToolError("spec must declare a list of tools")
    store = FixtureStore(spec_dir, spec.get("fixtures", {}))
    registry = ToolRegistry()
    for item in spec["tools"]:
        try:
            entry = contracts.tool_spec(item)
        except contracts.ContractError as error:
            raise ToolError(f"invalid tool declaration: {error}") from error
        builder = BUILTINS.get(entry["name"])
        if builder is None:
            raise ToolError(f"no built-in tool is named {entry['name']!r}")
        builder(registry, store, entry)
    return registry
