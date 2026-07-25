from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/support-v2-protocol"
SCRIPT = EXAMPLE / "run.py"
MANIFEST = EXAMPLE / "manifest.json"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_support_v2_example_is_external_cwd_provider_free_and_deterministic(
    tmp_path: Path,
) -> None:
    first = _run(cwd=tmp_path)
    repeated = _run(cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert repeated.returncode == 0, repeated.stderr
    assert repeated.stdout == first.stdout
    payload = json.loads(first.stdout)

    assert payload["schema"] == "pheroos-support-v2-example-result-v1"
    assert payload["provider_free"] is True
    assert payload["network_used"] is False
    assert payload["restart_rehydrated"] is True
    assert payload["authority_chain"] | {
        "verification_snapshot_root": "<root>",
        "membership_snapshot_root": "<root>",
        "support_snapshot_root": "<root>",
    } == {
        "verification_snapshot_root": "<root>",
        "membership_snapshot_root": "<root>",
        "support_snapshot_root": "<root>",
        "support_revision": 2,
    }
    assert payload["lease"] | {"lease_root": "<root>"} == {
        "lease_root": "<root>",
        "candidate_ref": "candidate:support-v2:accept",
        "active_cluster_count": 1,
        "policy_support_met": False,
    }
    assert payload["trace_event_types"] == [
        "principal_verification_set_advanced",
        "membership_epoch_committed",
        "support_state_advanced",
        "support_state_advanced",
        "support_lease_issued_v2",
    ]


def test_support_v2_example_uses_only_public_protocol_core_surfaces() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(name.startswith("pheroos.governance._") for name in imports)
    assert "pheroos.governance.support_v2" in imports
    assert "pheroos.governance.support" not in imports
    assert not any(name.startswith("tests.") for name in imports)
    assert imports & {"requests", "httpx", "urllib", "socket"} == set()


def test_support_v2_manifest_passes_protocol_v3_wire_validation(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pheroos.cli.main",
            "wire",
            "validate",
            "protocol-v3",
            str(MANIFEST),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "diagnostics": [],
        "ok": True,
        "report_version": "pheroos-wire-validation-report-v1",
        "subject": str(MANIFEST),
        "surface": "protocol-v3",
    }
