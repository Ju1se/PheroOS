from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "commit-certificate-v2-protocol"
SCRIPT = EXAMPLE / "run.py"


def _run(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_commit_certificate_example_is_external_cwd_and_deterministic(
    tmp_path: Path,
) -> None:
    first = _run(cwd=tmp_path)
    repeated = _run(cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert repeated.returncode == 0, repeated.stderr
    assert repeated.stdout == first.stdout
    payload = json.loads(first.stdout)
    assert payload["schema"] == "pheroos-commit-certificate-v2-example-result-v1"
    assert payload["provider_free"] is True
    assert payload["network_used"] is False
    assert payload["authority_source"] == ("trusted-issuer-attestation-verifier-v2")
    assert payload["implementations"] == [
        "pheroos-reference-certificate-verifier-v2",
        "stdlib-independent-certificate-verifier-v2",
    ]
    assert payload["results"] == [
        {
            "name": "commit_certificate_v2_contract",
            "ok": True,
            "detail": "",
        },
        {
            "name": "commit_certificate_v2_contract",
            "ok": True,
            "detail": "",
        },
    ]
    assert len(payload["proved_invariants"]) == 10


def test_commit_certificate_example_uses_public_conformance_only() -> None:
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
    assert "pheroos.conformance.checks.commit_certificate_v2_contract" in imports
