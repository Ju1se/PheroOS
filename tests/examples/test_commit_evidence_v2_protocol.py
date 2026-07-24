from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "commit-evidence-v2-protocol"
SCRIPT = EXAMPLE / "run.py"


def _run(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_commit_evidence_example_is_external_cwd_provider_free_and_deterministic(
    tmp_path: Path,
) -> None:
    first = _run(cwd=tmp_path)
    repeated = _run(cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert repeated.returncode == 0, repeated.stderr
    assert repeated.stdout == first.stdout
    payload = json.loads(first.stdout)
    assert payload["schema"] == "pheroos-commit-evidence-v2-example-result-v1"
    assert payload["provider_free"] is True
    assert payload["network_used"] is False
    assert payload["authority_source"] == "governance-state-store-v2"
    assert payload["result"] == {
        "name": "commit_evidence_v2_contract",
        "ok": True,
        "detail": "",
    }
    assert len(payload["proved_invariants"]) == 12
    assert "two_principal_qualified_success" in payload["proved_invariants"]
    assert "single_source_insufficient" in payload["proved_invariants"]


def test_commit_evidence_example_uses_the_public_conformance_surface_only() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(name.startswith("pheroos.governance._") for name in imports)
    assert not any(name.startswith("tests.") for name in imports)
    assert imports & {"requests", "httpx", "urllib", "socket"} == set()
    assert "pheroos.conformance.checks.commit_evidence_v2_contract" in imports
