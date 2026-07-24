from __future__ import annotations

import ast
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

import pheroos.governance as governance
from pheroos.governance._public_api import (
    COMPATIBILITY_MODULES,
    PUBLIC_API,
    PUBLIC_API_ORDER_SHA256,
)
from pheroos.conformance.public_api_inventory import load_public_api_inventory


ROOT = Path(__file__).resolve().parents[2]


def _run_child(source: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-c", source],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert isinstance(result, dict)
    return result


def test_lazy_facade_is_generated_from_the_canonical_static_inventory() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/generate_governance_public_api.py",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    inventory = load_public_api_inventory(ROOT)
    checked_exports = inventory["packages"]["pheroos.governance"]["exports"]
    assert set(governance.__all__) == {item["name"] for item in checked_exports}
    assert tuple(governance.__all__) == tuple(PUBLIC_API)
    assert len(governance.__all__) == len(set(governance.__all__))
    assert sha256("\n".join(governance.__all__).encode()).hexdigest() == (
        PUBLIC_API_ORDER_SHA256
    )


def test_type_checking_imports_make_every_lazy_export_statically_discoverable() -> None:
    tree = ast.parse(
        (ROOT / "pheroos/governance/__init__.py").read_text(encoding="utf-8")
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

    assert imported == set(governance.__all__)


def test_cold_import_has_no_functional_governance_side_effects() -> None:
    result = _run_child(
        """
import json
import sys
import pheroos.governance as governance

print(json.dumps({
    "cached": sorted(
        name for name in governance.__all__ if name in governance.__dict__
    ),
    "loaded": sorted(
        name
        for name in sys.modules
        if name == "pheroos" or name.startswith("pheroos.")
    ),
    "public_dir": sorted(name for name in dir(governance) if not name.startswith("_")),
}))
"""
    )

    assert result["cached"] == []
    assert result["loaded"] == [
        "pheroos",
        "pheroos._version",
        "pheroos.governance",
        "pheroos.governance._public_api",
    ]
    assert set(result["public_dir"]) == set(PUBLIC_API) | set(COMPATIBILITY_MODULES)


def test_first_lazy_access_is_thread_safe_and_imports_once() -> None:
    result = _run_child(
        """
import importlib
import json
from threading import Barrier, Lock, Thread
import time

import pheroos.governance as governance

original_import = governance._import_module
calls = []
values = []
errors = []
result_lock = Lock()
start = Barrier(33)

def counted_import(name):
    calls.append(name)
    time.sleep(0.01)
    return original_import(name)

def read_candidate():
    start.wait()
    try:
        value = governance.Candidate
    except BaseException as error:
        with result_lock:
            errors.append(repr(error))
    else:
        with result_lock:
            values.append(value)

governance._import_module = counted_import
threads = [Thread(target=read_candidate) for _ in range(32)]
for thread in threads:
    thread.start()
start.wait()
for thread in threads:
    thread.join()

canonical = importlib.import_module("pheroos.governance.candidate").Candidate
print(json.dumps({
    "calls": calls,
    "errors": errors,
    "same_identity": all(value is canonical for value in values),
    "value_count": len(values),
}))
"""
    )

    assert result == {
        "calls": ["pheroos.governance.candidate"],
        "errors": [],
        "same_identity": True,
        "value_count": 32,
    }


def test_from_import_star_import_and_every_binding_preserve_identity() -> None:
    from_namespace: dict[str, object] = {}
    exec(
        "from pheroos.governance import Candidate as imported_candidate",
        from_namespace,
    )
    assert (
        from_namespace["imported_candidate"]
        is import_module("pheroos.governance.candidate").Candidate
    )

    star_namespace: dict[str, object] = {}
    exec("from pheroos.governance import *", star_namespace)
    assert set(star_namespace) - {"__builtins__"} == set(governance.__all__)
    for name, (module_name, attribute) in PUBLIC_API.items():
        assert star_namespace[name] is getattr(import_module(module_name), attribute)


def test_pickle_inspect_and_type_hints_see_the_canonical_object() -> None:
    candidate = governance.Candidate
    canonical = import_module("pheroos.governance.candidate").Candidate

    assert candidate is canonical
    assert inspect.signature(candidate) == inspect.signature(canonical)
    assert get_type_hints(candidate) == get_type_hints(canonical)
    assert pickle.loads(pickle.dumps(candidate)) is candidate
    restored = pickle.loads(
        pickle.dumps(candidate(id="candidate-a", target="target-a"))
    )
    assert restored == candidate(id="candidate-a", target="target-a")
    assert type(restored) is candidate


def test_compatibility_modules_remain_lazy_and_discoverable() -> None:
    assert governance.attention is import_module("pheroos.governance.attention")
    assert "attention" in dir(governance)

    with pytest.raises(
        AttributeError,
        match="module 'pheroos.governance' has no attribute 'not_an_export'",
    ):
        governance.not_an_export


def test_cold_import_stays_within_the_governance_budget() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_governance_import.py",
            "--samples",
            "5",
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["median_ms"] <= result["budget_ms"] == 120.0
    assert all(
        observation["loaded_pheroos_modules"]
        == [
            "pheroos",
            "pheroos._version",
            "pheroos.governance",
            "pheroos.governance._public_api",
        ]
        for observation in result["observations"]
    )
    assert all(
        observation["cached_public_exports"] == []
        for observation in result["observations"]
    )
