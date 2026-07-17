from __future__ import annotations

import ast
import base64
from hashlib import sha256
from importlib import import_module
import inspect
import json
from pathlib import Path
import pickle
import subprocess
import sys
from typing import get_type_hints

import pytest

import pheroos.conformance as conformance
from pheroos.conformance._public_api import (
    COMPATIBILITY_MODULES,
    PUBLIC_API,
    PUBLIC_API_ORDER_SHA256,
)
from pheroos.conformance.public_api_inventory import load_public_api_inventory


ROOT = Path(__file__).resolve().parents[2]
LEGACY_PUBLIC_API_ORDER_SHA256 = (
    "1c44a26c233eca371ec560381807fc81adb6157452e79a9a9b5cd671316e24ae"
)
LEGACY_COMPATIBILITY_MODULES = {
    "checks": "pheroos.conformance.checks",
    "commit_tck": "pheroos.conformance.commit_tck",
    "commit_tck_v2_protocol": "pheroos.conformance.commit_tck_v2_protocol",
    "profile": "pheroos.conformance.profile",
    "public_api_inventory": "pheroos.conformance.public_api_inventory",
    "public_api_lifecycle": "pheroos.conformance.public_api_lifecycle",
    "report": "pheroos.conformance.report",
    "runner": "pheroos.conformance.runner",
}


def _run_child(source: str, *, isolated: bool = False, cwd: Path = ROOT) -> dict[str, object]:
    command = [sys.executable]
    if isolated:
        command.append("-I")
    command.extend(["-c", source])
    completed = subprocess.run(
        command,
        check=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert isinstance(result, dict)
    return result


def test_lazy_facade_matches_the_canonical_static_inventory() -> None:
    inventory = load_public_api_inventory(ROOT)
    checked_exports = inventory["packages"]["pheroos.conformance"]["exports"]
    expected = {
        item["name"]: (item["binding_owner"], item["attribute"])
        for item in checked_exports
    }

    assert dict(PUBLIC_API) == expected
    assert tuple(conformance.__all__) == tuple(PUBLIC_API)
    assert len(conformance.__all__) == len(set(conformance.__all__)) == 33
    observed_order_hash = sha256("\n".join(conformance.__all__).encode()).hexdigest()
    assert PUBLIC_API_ORDER_SHA256 == LEGACY_PUBLIC_API_ORDER_SHA256
    assert observed_order_hash == LEGACY_PUBLIC_API_ORDER_SHA256
    assert dict(COMPATIBILITY_MODULES) == LEGACY_COMPATIBILITY_MODULES


def test_type_checking_imports_make_every_lazy_export_statically_discoverable() -> None:
    tree = ast.parse(
        (ROOT / "pheroos/conformance/__init__.py").read_text(encoding="utf-8")
    )
    type_checking_blocks = [
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "TYPE_CHECKING"
    ]
    assert len(type_checking_blocks) == 1
    imported = {
        alias.asname or alias.name
        for node in type_checking_blocks[0].body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert imported == set(conformance.__all__)


def test_cold_import_has_no_functional_conformance_side_effects() -> None:
    result = _run_child(
        """
import json
import sys
import pheroos.conformance as conformance

print(json.dumps({
    "cached": sorted(
        name for name in conformance.__all__ if name in conformance.__dict__
    ),
    "loaded": sorted(
        name
        for name in sys.modules
        if name == "pheroos" or name.startswith("pheroos.")
    ),
    "public_dir": sorted(
        name for name in dir(conformance) if not name.startswith("_")
    ),
}))
"""
    )

    assert result["cached"] == []
    assert result["loaded"] == [
        "pheroos",
        "pheroos._version",
        "pheroos.conformance",
        "pheroos.conformance._public_api",
    ]
    assert set(result["public_dir"]) == set(PUBLIC_API) | set(COMPATIBILITY_MODULES)


def test_first_lazy_access_is_thread_safe_and_imports_once() -> None:
    result = _run_child(
        """
import importlib
import json
from threading import Barrier, Lock, Thread
import time

import pheroos.conformance as conformance

original_import = conformance._import_module
calls = []
values = []
errors = []
result_lock = Lock()
start = Barrier(33)

def counted_import(name):
    calls.append(name)
    time.sleep(0.01)
    return original_import(name)

def read_vector():
    start.wait()
    try:
        value = conformance.CommitTckVector
    except BaseException as error:
        with result_lock:
            errors.append(repr(error))
    else:
        with result_lock:
            values.append(value)

conformance._import_module = counted_import
threads = [Thread(target=read_vector) for _ in range(32)]
for thread in threads:
    thread.start()
start.wait()
for thread in threads:
    thread.join()

canonical = importlib.import_module(
    "pheroos.conformance.commit_tck"
).CommitTckVector
print(json.dumps({
    "calls": calls,
    "errors": errors,
    "same_identity": all(value is canonical for value in values),
    "value_count": len(values),
}))
"""
    )

    assert result == {
        "calls": ["pheroos.conformance.commit_tck"],
        "errors": [],
        "same_identity": True,
        "value_count": 32,
    }


def test_from_import_star_import_and_every_binding_preserve_identity() -> None:
    from_namespace: dict[str, object] = {}
    exec(
        "from pheroos.conformance import CommitTckVector as imported_vector",
        from_namespace,
    )
    assert from_namespace["imported_vector"] is import_module(
        "pheroos.conformance.commit_tck"
    ).CommitTckVector

    star_namespace: dict[str, object] = {}
    exec("from pheroos.conformance import *", star_namespace)
    assert set(star_namespace) - {"__builtins__"} == set(conformance.__all__)
    for name, (module_name, attribute) in PUBLIC_API.items():
        assert star_namespace[name] is getattr(import_module(module_name), attribute)


def test_pickle_inspect_and_type_hints_see_the_canonical_object() -> None:
    vector = conformance.CommitTckVector
    canonical = import_module("pheroos.conformance.commit_tck").CommitTckVector

    assert vector is canonical
    assert inspect.signature(vector) == inspect.signature(canonical)
    assert get_type_hints(vector) == get_type_hints(canonical)
    assert pickle.loads(pickle.dumps(vector)) is vector


@pytest.mark.parametrize(
    "name",
    [
        "CommitTckAdapter",
        "CommitTckReport",
        "CommitTckResult",
        "CommitTckVector",
        "ReferenceCommitTckAdapter",
        "commit_tck_artifact_root",
        "commit_tck_schema",
        "load_commit_tck_vectors",
        "run_commit_tck",
    ],
)
def test_every_canonicalized_commit_tck_export_has_resolvable_hints(
    name: str,
) -> None:
    value = getattr(conformance, name)
    canonical = getattr(import_module("pheroos.conformance.commit_tck"), name)

    assert value is canonical
    assert get_type_hints(value) == get_type_hints(canonical)


def test_commit_tck_artifact_path_does_not_load_the_reference_runtime() -> None:
    result = _run_child(
        """
import json
import sys

import pheroos.conformance.commit_tck as commit_tck

artifact_root = commit_tck.commit_tck_artifact_root()
print(json.dumps({
    "artifact_root": artifact_root,
    "reference_cached": "ReferenceCommitTckAdapter" in commit_tck.__dict__,
    "reference_loaded": (
        "pheroos.conformance._commit_tck.reference_adapter" in sys.modules
    ),
    "governance_loaded": any(
        name == "pheroos.governance" or name.startswith("pheroos.governance.")
        for name in sys.modules
    ),
}))
"""
    )

    assert result["artifact_root"].startswith("sha256:")
    assert result["reference_cached"] is False
    assert result["reference_loaded"] is False
    assert result["governance_loaded"] is False


def test_commit_tck_reference_adapter_resolves_once_and_preserves_pickle() -> None:
    result = _run_child(
        """
import importlib
import json
import pickle
from threading import Barrier, Lock, Thread
import time

import pheroos.conformance.commit_tck as commit_tck

original_import = commit_tck._import_module
calls = []
errors = []
values = []
result_lock = Lock()
start = Barrier(9)

def counted_import(name):
    calls.append(name)
    time.sleep(0.01)
    return original_import(name)

def read_adapter():
    start.wait()
    try:
        value = commit_tck.ReferenceCommitTckAdapter
    except BaseException as error:
        with result_lock:
            errors.append(repr(error))
    else:
        with result_lock:
            values.append(value)

commit_tck._import_module = counted_import
threads = [Thread(target=read_adapter) for _ in range(8)]
for thread in threads:
    thread.start()
start.wait()
for thread in threads:
    thread.join()

canonical = importlib.import_module(
    "pheroos.conformance._commit_tck.reference_adapter"
).ReferenceCommitTckAdapter
adapter_type = commit_tck.ReferenceCommitTckAdapter
restored = pickle.loads(pickle.dumps(adapter_type()))
print(json.dumps({
    "calls": calls,
    "errors": errors,
    "module": adapter_type.__module__,
    "pickle_identity": type(restored) is adapter_type,
    "same_identity": all(value is canonical for value in values),
    "value_count": len(values),
}))
"""
    )

    assert result == {
        "calls": ["pheroos.conformance._commit_tck.reference_adapter"],
        "errors": [],
        "module": "pheroos.conformance.commit_tck",
        "pickle_identity": True,
        "same_identity": True,
        "value_count": 8,
    }


def test_cold_process_unpickles_the_public_reference_adapter() -> None:
    payload = base64.b64encode(
        pickle.dumps(conformance.ReferenceCommitTckAdapter())
    ).decode("ascii")
    result = _run_child(
        f"""
import base64
import json
import pickle

import pheroos.conformance.commit_tck as commit_tck

initially_uncached = "ReferenceCommitTckAdapter" not in commit_tck.__dict__
restored = pickle.loads(base64.b64decode({payload!r}))
adapter_type = commit_tck.ReferenceCommitTckAdapter
print(json.dumps({{
    "cached_after": "ReferenceCommitTckAdapter" in commit_tck.__dict__,
    "initially_uncached": initially_uncached,
    "module": type(restored).__module__,
    "type_identity": type(restored) is adapter_type,
}}))
"""
    )

    assert result == {
        "cached_after": True,
        "initially_uncached": True,
        "module": "pheroos.conformance.commit_tck",
        "type_identity": True,
    }


def test_root_owned_store_exports_restore_through_fresh_lazy_facade_pickle() -> None:
    result = _run_child(
        """
import importlib
import json
import pickle

import pheroos.conformance as conformance

bindings = {
    "GovernanceStateStoreConformanceAdapter": (
        "pheroos.conformance.checks.authority_ledger_contract"
    ),
    "ReferenceGovernanceStateStoreConformanceAdapter": (
        "pheroos.conformance.checks.authority_ledger_contract"
    ),
    "run_governance_state_store_conformance": (
        "pheroos.conformance.checks.authority_ledger_contract"
    ),
    "TraceStoreConformanceAdapter": (
        "pheroos.conformance.checks.trace_store_contract"
    ),
    "ReferenceTraceStoreConformanceAdapter": (
        "pheroos.conformance.checks.trace_store_contract"
    ),
    "run_trace_store_conformance": (
        "pheroos.conformance.checks.trace_store_contract"
    ),
}
canonical = {
    name: getattr(importlib.import_module(module_name), name)
    for name, module_name in bindings.items()
}
initially_uncached = all(name not in conformance.__dict__ for name in bindings)
object_round_trips = {
    name: pickle.loads(pickle.dumps(value)) is value
    for name, value in canonical.items()
}
cached_after = all(name in conformance.__dict__ for name in bindings)
root_identity = all(
    getattr(conformance, name) is value for name, value in canonical.items()
)
instance_round_trips = {}
for name in (
    "ReferenceGovernanceStateStoreConformanceAdapter",
    "ReferenceTraceStoreConformanceAdapter",
):
    adapter_type = canonical[name]
    restored = pickle.loads(pickle.dumps(adapter_type()))
    instance_round_trips[name] = type(restored) is adapter_type

print(json.dumps({
    "cached_after": cached_after,
    "initially_uncached": initially_uncached,
    "instance_round_trips": instance_round_trips,
    "object_round_trips": object_round_trips,
    "root_identity": root_identity,
}))
"""
    )

    assert result == {
        "cached_after": True,
        "initially_uncached": True,
        "instance_round_trips": {
            "ReferenceGovernanceStateStoreConformanceAdapter": True,
            "ReferenceTraceStoreConformanceAdapter": True,
        },
        "object_round_trips": {
            "GovernanceStateStoreConformanceAdapter": True,
            "ReferenceGovernanceStateStoreConformanceAdapter": True,
            "run_governance_state_store_conformance": True,
            "TraceStoreConformanceAdapter": True,
            "ReferenceTraceStoreConformanceAdapter": True,
            "run_trace_store_conformance": True,
        },
        "root_identity": True,
    }


def test_compatibility_modules_remain_lazy_and_discoverable() -> None:
    for name, module_name in LEGACY_COMPATIBILITY_MODULES.items():
        assert getattr(conformance, name) is import_module(module_name)
        assert name in dir(conformance)

    with pytest.raises(
        AttributeError,
        match="module 'pheroos.conformance' has no attribute 'not_an_export'",
    ):
        conformance.not_an_export


def test_external_cwd_isolated_import_preserves_public_abi(tmp_path: Path) -> None:
    result = _run_child(
        """
import importlib
import json
import pheroos.conformance as conformance
from pheroos.conformance import CommitTckVector

canonical = importlib.import_module(
    "pheroos.conformance.commit_tck"
).CommitTckVector
print(json.dumps({
    "count": len(conformance.__all__),
    "identity": CommitTckVector is canonical,
    "module": CommitTckVector.__module__,
}))
""",
        isolated=True,
        cwd=tmp_path,
    )

    assert result == {
        "count": 33,
        "identity": True,
        "module": "pheroos.conformance.commit_tck",
    }
