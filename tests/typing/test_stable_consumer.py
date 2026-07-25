from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

from pheroos.conformance.public_api_inventory import PUBLIC_PACKAGES
from pheroos.conformance.stable_api_candidate import load_stable_api_candidate
from pheroos.conformance.stable_api_roots import STABLE_API_FORBIDDEN_BINDINGS


ROOT = Path(__file__).resolve().parents[2]
CONSUMER = ROOT / "tests" / "typing" / "stable_consumer.py"
# The independent Store is deliberately a harness-owned Draft/conformance
# fixture.  stable_consumer.py sees only the promotion-candidate Protocol.
_INDEPENDENT_WRITE_JOURNEY_HARNESS = (
    "from stable_consumer import exercise_governance_write_journey;"
    "from pheroos.conformance.authority_store_v2_spec_adapter import "
    "IndependentStdlibGovernanceStateStoreV2Adapter;"
    "exercise_governance_write_journey("
    "IndependentStdlibGovernanceStateStoreV2Adapter())"
)


def _candidate_bindings() -> tuple[set[str], set[str]]:
    candidate = load_stable_api_candidate(ROOT)
    closure = {
        entry["binding"]
        for package in candidate["packages"].values()
        for entry in package["exports"]
    }
    roots = {
        f"{package_name}.{name}"
        for package_name, package in candidate["packages"].items()
        for name in package["roots"]
    }
    return closure, roots


def _consumer_imports() -> set[str]:
    tree = ast.parse(CONSUMER.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if not node.module.startswith("pheroos"):
            continue
        assert node.module in PUBLIC_PACKAGES
        imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imports


def test_consumer_imports_every_candidate_root_only_through_six_facades() -> None:
    closure, roots = _candidate_bindings()
    imported = _consumer_imports()

    assert roots <= imported
    assert imported <= closure
    assert imported.isdisjoint(STABLE_API_FORBIDDEN_BINDINGS)


def test_stable_consumer_has_zero_strict_mypy_errors() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--follow-imports=silent",
            str(CONSUMER),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Success: no issues found" in completed.stdout


def test_stable_consumer_runtime_journey_is_provider_free() -> None:
    completed = subprocess.run(
        [sys.executable, str(CONSUMER)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_governance_write_store_is_external_and_harness_owned() -> None:
    tree = ast.parse(CONSUMER.read_text(encoding="utf-8"))
    journey = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "exercise_governance_write_journey"
    )
    adapter = journey.args.args[0]

    assert adapter.arg == "adapter"
    assert adapter.annotation is not None
    assert ast.unparse(adapter.annotation) == "GovernanceStateStoreConformanceAdapterV2"
    assert (
        "IndependentStdlibGovernanceStateStoreV2Adapter"
        in _INDEPENDENT_WRITE_JOURNEY_HARNESS
    )
    assert (
        "ReferenceGovernanceStateStoreConformanceAdapterV2"
        not in _INDEPENDENT_WRITE_JOURNEY_HARNESS
    )


def test_stable_consumer_executes_governance_write_and_denial_journeys() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys;"
                f"sys.path.insert(0, {str(CONSUMER.parent)!r});"
                f"{_INDEPENDENT_WRITE_JOURNEY_HARNESS}"
            ),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
