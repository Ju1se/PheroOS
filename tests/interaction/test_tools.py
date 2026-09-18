"""Tool declarations, fixture reads and built-in checkers; no network, no session, no clock."""

from hashlib import sha256
import os

import pytest

from pheroos_interaction.runner import contracts
from pheroos_interaction.runner.tools import (CANDIDATE_SCHEMA, FixtureStore, fixture_read_schema,
                                              ToolError, ToolRegistry, build_registry)

ORDERS = {"orders": [{"id": "a", "category": "books", "amount_cents": 1000},
                     {"id": "b", "category": "apples", "amount_cents": 250},
                     {"id": "c", "category": "books", "amount_cents": 500}]}
EXPECTED = {"totals": [{"category": "apples", "cents": 250}, {"category": "books", "cents": 1500}],
            "total_cents": 1750}
MODEL = {"provider": "fake", "model": "fake-model", "max_new_tokens": 512,
         "prompt_token_bound": 8192, "prompt_overhead_tokens": 600}
TASK_LIMITS = {"model_steps": 4, "tool_calls": 4, "rejections": 2, "calls": 8, "tokens": 4096}
RUN_LIMITS = {"max_calls": 64, "token_cap": 65536, "context_bytes": 65536, "artifact_bytes": 65536,
              "max_work_items": 8, "max_children": 4, "max_depth": 2, "max_platform_operations": 128}
CANDIDATE_OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["totals", "total_cents"],
    "properties": {"totals": {"type": "array", "maxItems": 64,
                              "items": {"type": "object", "additionalProperties": False,
                                        "required": ["category", "cents"],
                                        "properties": {"category": {"type": "string", "maxLength": 64},
                                                       "cents": {"type": "integer", "minimum": 0}}}},
                   "total_cents": {"type": "integer", "minimum": 0}}}
REVIEW_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verdict"],
                 "properties": {"verdict": {"type": "boolean"}}}


def fingerprint(relative, raw):
    return {"path": relative, "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}


def declare(root, relative, value):
    raw = value if type(value) is bytes else contracts.wire(value).encode()
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return fingerprint(relative, raw)


def artifact(ref, value):
    return {"ref": ref, "work_id": "produce", "version": 1, "kind": "output",
            "value": value, "digest": contracts.digest(value)}


def registry_for(root, fixtures, *tools):
    return build_registry({"fixtures": fixtures, "tools": list(tools)}, root)


def execute_nothing(arguments, resolver):
    return {}


def register(registry, name="demo.tool", **overrides):
    options = {"version": "v1", "description": "a declared test tool",
               "schema": fixture_read_schema(["orders"]), "execute": execute_nothing}
    options.update(overrides)
    registry.register(name, **options)


class Resolver:
    """Answers only from a declared map, recording every ref it was asked for."""

    def __init__(self, artifacts=None):
        self.artifacts = dict(artifacts or {})
        self.reads = []

    def read_artifact(self, ref):
        self.reads.append(ref)
        return self.artifacts.get(ref)


class Spy:
    """A registered execute that records the arguments and resolver it was given."""

    def __init__(self, result=None):
        self.calls = []
        self.result = {"ok": True} if result is None else result

    def __call__(self, arguments, resolver):
        self.calls.append((arguments, resolver))
        return self.result


@pytest.fixture
def declarations(tmp_path):
    return {"orders": declare(tmp_path, "fixtures/orders.json", ORDERS),
            "expected": declare(tmp_path, "fixtures/expected.json", EXPECTED)}


@pytest.fixture
def store(tmp_path, declarations):
    return FixtureStore(tmp_path, declarations)


@pytest.fixture
def spec(declarations):
    return contracts.workflow_spec({
        "format": contracts.SPEC_FORMAT, "run_id": "example",
        "agents": [{"id": "producer", "model": MODEL, "capabilities": {"tools": ["fixture.read"]}},
                   {"id": "reviewer", "model": MODEL, "capabilities": {"tools": ["checker.category_totals"]}}],
        "tools": [{"name": "fixture.read", "version": "fixture-read-v1", "config": {"fixtures": ["expected", "orders"]}},
                  {"name": "checker.category_totals", "version": "category-totals-v1",
                   "config": {"fixture": "orders"}},
                  {"name": "checker.expected_json", "version": "expected-json-v1",
                   "config": {"fixture": "expected"}}],
        "fixtures": declarations,
        "tasks": [{"id": "produce", "kind": "model", "agent": "producer", "instructions": "total the orders",
                   "dependencies": [], "reads": [], "tools": ["fixture.read"],
                   "output_schema": CANDIDATE_OUTPUT_SCHEMA, "limits": TASK_LIMITS},
                  {"id": "review", "kind": "model", "agent": "reviewer", "instructions": "check the totals",
                   "dependencies": ["produce"], "reads": ["produce"], "tools": ["checker.category_totals"],
                   "output_schema": REVIEW_SCHEMA, "limits": TASK_LIMITS},
                  {"id": "decide", "kind": "host", "agent": "host",
                   "dependencies": ["produce", "review"], "reads": ["produce", "review"],
                   "rule": {"type": "checker_pass", "candidate": "produce", "review": "review",
                            "checker": "checker.category_totals"}}],
        "limits": RUN_LIMITS})


@pytest.fixture
def registry(spec, tmp_path):
    return build_registry(spec, tmp_path)


# ---------------------------------------------------------------- registration

def test_register_rejects_reserved_malformed_and_duplicate_names():
    registry = ToolRegistry()
    register(registry)
    for name in contracts.RESERVED_TOOLS + ("Demo", "1tool", "demo tool", "x" * 65, "", 7, "demo.tool"):
        with pytest.raises(ToolError):
            register(registry, name)
    assert registry.names() == ["demo.tool"]


def test_register_rejects_invalid_and_non_object_schemas():
    registry = ToolRegistry()
    schemas = ({"type": "array", "items": {"type": "string", "maxLength": 8}, "maxItems": 4},
               {"type": "string", "maxLength": 8},
               {"type": "object", "properties": {}, "additionalProperties": True},
               {"type": "object", "properties": {}, "patternProperties": {}},
               {"type": "widget"}, "not a schema")
    for index, schema in enumerate(schemas):
        with pytest.raises(ToolError):
            register(registry, f"demo.s{index}", schema=schema)
    assert registry.names() == []


def test_register_rejects_a_bad_version_description_execute_or_bound():
    registry = ToolRegistry()
    bad = ({"version": ""}, {"version": "   "}, {"version": "v" * 65}, {"version": 1},
           {"description": ""}, {"description": "d" * 1025}, {"description": None},
           {"execute": "not callable"}, {"output_bytes": 0}, {"output_bytes": -1},
           {"output_bytes": True}, {"output_bytes": "8192"})
    for index, overrides in enumerate(bad):
        with pytest.raises(ToolError):
            register(registry, f"demo.b{index}", **overrides)
    assert registry.names() == []


def test_registry_reports_declared_tools_and_refuses_unknown_names(registry):
    assert registry.names() == ["checker.category_totals", "checker.expected_json", "fixture.read"]
    assert registry.version("fixture.read") == "fixture-read-v1"
    assert registry.output_bytes("fixture.read") == 8192
    assert registry.schema("fixture.read") == contracts.validate_schema(fixture_read_schema(["expected", "orders"]))
    assert registry.schema("checker.expected_json") == contracts.validate_schema(CANDIDATE_SCHEMA)
    for unknown in ("checker.absent", 7):
        for accessor in (registry.version, registry.schema, registry.output_bytes, registry.declaration):
            with pytest.raises(ToolError):
                accessor(unknown)


def test_declarations_are_provider_shaped_ordered_and_independent(registry):
    declaration = registry.declaration("fixture.read")
    assert set(declaration) == {"name", "description", "input_schema"}
    assert declaration["name"] == "fixture.read" and declaration["description"].strip()
    assert declaration["input_schema"]["required"] == ["name"]
    declaration["input_schema"]["properties"].clear()
    assert registry.declaration("fixture.read")["input_schema"]["properties"]
    registry.schema("fixture.read")["properties"].clear()
    assert registry.schema("fixture.read")["properties"]
    ordered = registry.declarations(["checker.expected_json", "fixture.read"])
    assert [item["name"] for item in ordered] == ["checker.expected_json", "fixture.read"]
    with pytest.raises(ToolError):
        registry.declarations("fixture.read")


# ---------------------------------------------------------------- execution

def test_execute_refuses_nonconforming_arguments_before_running_the_tool():
    spy = Spy()
    registry = ToolRegistry()
    register(registry, "demo.spy", execute=spy)
    for arguments in ({"name": "orders", "capabilities": ["*"]}, {"name": 7}, {}, {"name": ""},
                      {"name": "x" * 65}):
        with pytest.raises(ToolError, match="do not conform"):
            registry.execute("demo.spy", arguments, None)
    assert spy.calls == []


def test_execute_refuses_non_object_and_non_finite_arguments():
    spy = Spy()
    registry = ToolRegistry()
    register(registry, "demo.spy", execute=spy)
    for arguments in ([], "orders", None, {"name": float("nan")}):
        with pytest.raises(ToolError):
            registry.execute("demo.spy", arguments, None)
    with pytest.raises(ToolError):
        registry.execute("demo.absent", {"name": "orders"}, None)
    assert spy.calls == []


def test_execute_passes_a_validated_copy_and_the_resolver():
    spy = Spy({"echo": True})
    registry = ToolRegistry()
    register(registry, "demo.spy", execute=spy)
    arguments, resolver = {"name": "orders"}, Resolver()
    assert registry.execute("demo.spy", arguments, resolver) == {"echo": True}
    observed, seen = spy.calls[0]
    assert observed == {"name": "orders"} and observed is not arguments and seen is resolver
    arguments["name"] = "mutated"
    assert spy.calls[0][0] == {"name": "orders"}


def test_execute_bounds_the_output_bytes():
    registry = ToolRegistry()
    payload = {"payload": "x" * 64}
    exact = len(contracts.wire(payload).encode())
    register(registry, "demo.exact", execute=lambda arguments, resolver: payload, output_bytes=exact)
    register(registry, "demo.over", execute=lambda arguments, resolver: payload, output_bytes=exact - 1)
    assert registry.execute("demo.exact", {"name": "orders"}, None) == payload
    with pytest.raises(ToolError, match="exceeds"):
        registry.execute("demo.over", {"name": "orders"}, None)


def test_execute_refuses_a_non_object_or_non_finite_output():
    registry = ToolRegistry()
    for index, result in enumerate(([], "text", None, {"value": float("inf")}, {"value": float("nan")})):
        register(registry, f"demo.o{index}", execute=lambda arguments, resolver, result=result: result)
        with pytest.raises(ToolError):
            registry.execute(f"demo.o{index}", {"name": "orders"}, None)


# ---------------------------------------------------------------- fixture store

def test_store_lists_and_copies_declarations(store, declarations):
    assert store.names() == ["expected", "orders"]
    entry = store.declaration("orders")
    assert entry == declarations["orders"]
    entry["sha256"] = "0" * 64
    assert store.declaration("orders")["sha256"] == declarations["orders"]["sha256"]
    for unknown in ("absent", 7):
        with pytest.raises(ToolError):
            store.declaration(unknown)
        with pytest.raises(ToolError):
            store.read(unknown)


def test_store_rejects_traversing_absolute_and_malformed_declarations(tmp_path, declarations):
    good = declarations["orders"]
    for path in ("../orders.json", "/etc/passwd", "fixtures/../orders.json", "fixtures\\orders.json",
                 "./orders.json", "", "fixtures//orders.json"):
        with pytest.raises(ToolError):
            FixtureStore(tmp_path, {"orders": {**good, "path": path}})
    for fixtures in ({"Orders": good}, {"orders": {**good, "sha256": "zz"}}, {"orders": {"path": "x.json"}},
                     {7: good}, []):
        with pytest.raises(ToolError):
            FixtureStore(tmp_path, fixtures)


def test_store_refuses_to_follow_a_symlinked_file(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    raw = contracts.wire(ORDERS).encode()
    (tmp_path / "outside.json").write_bytes(raw)
    (root / "real.json").write_bytes(raw)
    os.symlink(tmp_path / "outside.json", root / "link_out.json")
    os.symlink(root / "real.json", root / "link_in.json")
    store = FixtureStore(root, {"real": fingerprint("real.json", raw),
                                "out": fingerprint("link_out.json", raw),
                                "inside": fingerprint("link_in.json", raw)})
    assert store.read("real") == raw
    for name in ("out", "inside"):
        with pytest.raises(ToolError):
            store.read(name)


def test_store_refuses_a_symlinked_intermediate_directory(tmp_path):
    root = tmp_path / "root"
    (root / "real").mkdir(parents=True)
    raw = contracts.wire(ORDERS).encode()
    (root / "real" / "data.json").write_bytes(raw)
    os.symlink(root / "real", root / "link")
    store = FixtureStore(root, {"direct": fingerprint("real/data.json", raw),
                                "linked": fingerprint("link/data.json", raw)})
    assert store.read("direct") == raw
    with pytest.raises(ToolError):
        store.read("linked")


def test_store_rejects_a_missing_file_or_a_directory(tmp_path):
    (tmp_path / "folder").mkdir()
    store = FixtureStore(tmp_path, {"gone": fingerprint("gone.json", b"{}"),
                                    "folder": fingerprint("folder", b"{}")})
    with pytest.raises(ToolError, match="cannot be opened"):
        store.read("gone")
    with pytest.raises(ToolError, match="regular file"):
        store.read("folder")


def test_store_rejects_a_size_or_a_digest_mismatch(tmp_path, store):
    path = tmp_path / "fixtures" / "orders.json"
    raw = path.read_bytes()
    path.write_bytes(raw + b" ")
    with pytest.raises(ToolError, match="were declared"):
        store.read("orders")
    swapped = raw.replace(b"1000", b"1001")
    assert len(swapped) == len(raw) and swapped != raw
    path.write_bytes(swapped)
    with pytest.raises(ToolError) as failure:
        store.read("orders")
    assert "orders" in str(failure.value) and "sha256" in str(failure.value)


def test_store_reads_the_exact_declared_bytes(tmp_path, store):
    assert store.read("orders") == contracts.wire(ORDERS).encode()
    assert store.read("expected") == contracts.wire(EXPECTED).encode()
    empty = FixtureStore(tmp_path, {"empty": declare(tmp_path, "empty.json", b"")})
    assert empty.read("empty") == b""


# ---------------------------------------------------------------- built-in tools

def test_fixture_read_reports_bytes_digest_and_content(registry, store, tmp_path):
    raw = (tmp_path / "fixtures" / "orders.json").read_bytes()
    assert registry.execute("fixture.read", {"name": "orders"}, None) == {
        "name": "orders", "bytes": len(raw), "digest": sha256(raw).hexdigest(), "content": ORDERS}
    with pytest.raises(ToolError, match="do not conform"):
        registry.execute("fixture.read", {"name": "absent"}, None)   # outside the tool's scope
    with pytest.raises(ToolError, match="not declared"):
        store.read("absent")


def test_fixture_read_rejects_duplicate_keys_and_nonfinite_constants(tmp_path):
    for index, raw in enumerate((b'{"a": 1, "a": 2}', b'{"a": NaN}', b'{"a": Infinity}', b'{"a": ')):
        relative = f"raw{index}.json"
        (tmp_path / relative).write_bytes(raw)
        built = registry_for(tmp_path, {"raw": fingerprint(relative, raw)},
                             {"name": "fixture.read", "version": "v1", "config": {"fixtures": ["raw"]}})
        with pytest.raises(ToolError):
            built.execute("fixture.read", {"name": "raw"}, None)


def test_category_totals_passes_and_digests_the_resolved_value(registry):
    resolver = Resolver({"produce:1": artifact("produce:1", EXPECTED)})
    result = registry.execute("checker.category_totals", {"candidate_ref": "produce:1"}, resolver)
    assert result == {"candidate_ref": "produce:1", "candidate_digest": contracts.digest(EXPECTED),
                      "pass": True, "detail": {"expected_total_cents": 1750, "mismatches": []}}
    assert resolver.reads == ["produce:1"]


def test_one_cent_changes_the_verdict_and_the_candidate_digest(registry):
    changed = {"totals": [{"category": "apples", "cents": 251}, {"category": "books", "cents": 1500}],
               "total_cents": 1751}
    resolver = Resolver({"a": artifact("a", EXPECTED), "b": artifact("b", changed)})
    passed = registry.execute("checker.category_totals", {"candidate_ref": "a"}, resolver)
    failed = registry.execute("checker.category_totals", {"candidate_ref": "b"}, resolver)
    assert passed["pass"] is True and failed["pass"] is False
    assert failed["candidate_digest"] == contracts.digest(changed) != passed["candidate_digest"]
    assert any("apples" in mismatch for mismatch in failed["detail"]["mismatches"])


@pytest.mark.parametrize("candidate, fragment", [
    (["totals"], "not an object"),
    ({"totals": EXPECTED["totals"]}, "missing fields total_cents"),
    ({"totals": list(reversed(EXPECTED["totals"])), "total_cents": 1750}, "not sorted"),
    ({"totals": [{"category": "apples", "cents": 100}, {"category": "apples", "cents": 150},
                 {"category": "books", "cents": 1500}], "total_cents": 1750}, "duplicate category apples"),
    ({"totals": [{"category": "books", "cents": 1500}], "total_cents": 1750}, "missing category apples"),
    ({"totals": EXPECTED["totals"] + [{"category": "cider", "cents": 0}], "total_cents": 1750},
     "unexpected category cider"),
    ({"totals": [{"category": "apples", "cents": 250}, {"category": "books", "cents": 1499}],
      "total_cents": 1750}, "books: expected 1500 cents, got 1499"),
    ({"totals": EXPECTED["totals"], "total_cents": 9999}, "total_cents: expected 1750"),
])
def test_category_totals_reports_each_structural_mismatch(registry, candidate, fragment):
    resolver = Resolver({"c": artifact("c", candidate)})
    result = registry.execute("checker.category_totals", {"candidate_ref": "c"}, resolver)
    assert result["pass"] is False
    assert any(fragment in mismatch for mismatch in result["detail"]["mismatches"])
    assert len(result["detail"]["mismatches"]) <= 8


def test_category_totals_requires_a_visible_candidate_and_a_resolver(registry):
    with pytest.raises(ToolError, match="not visible"):
        registry.execute("checker.category_totals", {"candidate_ref": "absent"}, Resolver())
    with pytest.raises(ToolError, match="resolver"):
        registry.execute("checker.category_totals", {"candidate_ref": "absent"}, object())
    with pytest.raises(ToolError, match="malformed artifact"):
        registry.execute("checker.category_totals", {"candidate_ref": "x"},
                         Resolver({"x": {"ref": "x", "digest": "0" * 64}}))


def test_category_totals_rejects_a_malformed_declared_fixture(tmp_path):
    for content in ({"orders": "nope"}, {"orders": [{"id": "a", "category": "books"}]},
                    {"orders": [{"id": "a", "category": "books", "amount_cents": -1}]},
                    {"orders": [], "extra": 1}):
        built = registry_for(tmp_path, {"orders": declare(tmp_path, "orders.json", content)},
                             {"name": "checker.category_totals", "version": "v1",
                              "config": {"fixture": "orders"}})
        with pytest.raises(ToolError, match="fixture 'orders'"):
            built.execute("checker.category_totals", {"candidate_ref": "c"},
                          Resolver({"c": artifact("c", EXPECTED)}))


def test_expected_json_compares_canonical_serializations(registry):
    other = {"total_cents": 1750, "totals": []}
    resolver = Resolver({"same": artifact("same", dict(reversed(list(EXPECTED.items())))),
                         "other": artifact("other", other)})
    same = registry.execute("checker.expected_json", {"candidate_ref": "same"}, resolver)
    assert same["pass"] is True and same["candidate_digest"] == contracts.digest(EXPECTED)
    assert same["detail"] == {"expected_digest": contracts.digest(EXPECTED)}
    unequal = registry.execute("checker.expected_json", {"candidate_ref": "other"}, resolver)
    assert unequal["pass"] is False and unequal["candidate_digest"] == contracts.digest(other)
    assert unequal["detail"] == {"expected_digest": contracts.digest(EXPECTED)}


# ---------------------------------------------------------------- registry construction

def test_build_registry_registers_exactly_the_declared_tools(spec, registry):
    assert registry.names() == sorted(tool["name"] for tool in spec["tools"])
    assert [registry.version(name) for name in registry.names()] == [
        "category-totals-v1", "expected-json-v1", "fixture-read-v1"]
    assert all(registry.declaration(name)["description"].strip() for name in registry.names())


def test_build_registry_rejects_an_unknown_tool_name_or_an_invalid_config(tmp_path, declarations):
    with pytest.raises(ToolError, match="built-in"):
        registry_for(tmp_path, declarations, {"name": "checker.unknown", "version": "v1"})
    with pytest.raises(ToolError):
        registry_for(tmp_path, declarations, {"name": "fixture.read", "version": "v1", "config": {"fixtures": ["orders"]}},
                     {"name": "fixture.read", "version": "v1", "config": {"fixtures": ["orders"]}})
    for broken in ({"tools": [], "fixtures": []}, {"tools": {}, "fixtures": {}}, "spec"):
        with pytest.raises(ToolError):
            build_registry(broken, tmp_path)
    for entry in ({"name": "checker.category_totals", "version": "v1", "config": {"fixture": "absent"}},
                  {"name": "checker.category_totals", "version": "v1"},
                  {"name": "checker.expected_json", "version": "v1", "config": {"fixture": "orders", "n": 1}},
                  {"name": "fixture.read", "version": "v1", "config": {"fixture": "orders"}},
                  {"name": "fixture.read", "version": ""}):
        with pytest.raises(ToolError):
            registry_for(tmp_path, declarations, entry)


def test_repeated_execution_is_byte_identical(registry):
    resolver = Resolver({"r": artifact("r", EXPECTED)})
    calls = (("checker.category_totals", {"candidate_ref": "r"}),
             ("checker.expected_json", {"candidate_ref": "r"}),
             ("fixture.read", {"name": "orders"}))
    for name, arguments in calls:
        first = registry.execute(name, arguments, resolver)
        second = registry.execute(name, arguments, resolver)
        assert contracts.wire(first) == contracts.wire(second)
