from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "risk-v2-protocol"
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


def test_risk_v2_example_is_external_cwd_provider_free_and_deterministic(
    tmp_path: Path,
) -> None:
    first = _run(cwd=tmp_path)
    repeated = _run(cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert repeated.returncode == 0, repeated.stderr
    assert repeated.stdout == first.stdout
    payload = json.loads(first.stdout)

    assert payload["schema"] == "pheroos-risk-v2-example-result-v1"
    assert payload["manifest"] | {"manifest_root": "<root>"} == {
        "schema_version": "pheroos-protocol-schema-v3",
        "protocol_id": "risk.durable-state",
        "protocol_version": "pheroos.protocol.v2",
        "manifest_root": "<root>",
    }
    assert payload["reference_store"] == {
        "implementation": "reference-conformance-adapter:test-only",
        "restart_between_epochs": True,
        "fresh_reader_identity": True,
        "production_persistence": False,
    }
    assert payload["grant"] == {
        "operation": "qualify_evidence",
        "issuer_ref": "issuer:risk-v2-example",
        "expires_at_epoch": 1_000,
    }
    assert payload["portable"] | {
        "canonical_bytes_sha256": "<root>",
        "request_root": "<root>",
    } == {
        "canonical_bytes_sha256": "<root>",
        "request_root": "<root>",
        "rehydrated_by_fresh_reader": True,
        "verified_source_serialized": False,
    }
    lineage = payload["lineage"]
    assert lineage | {"stream_ref": "<stream>"} == {
        "stream_ref": "<stream>",
        "same_stream_across_epoch_jump": True,
        "first_epoch": 7,
        "next_epoch": 137,
        "next_parent_epoch": 7,
        "revisions": [1, 2],
        "window_reset_required": True,
        "positions": ["superseded", "current"],
    }
    assert payload["trace_events"] == [
        ["risk_state_advanced", "risk_assessed_v2"],
        ["risk_state_advanced", "risk_assessed_v2"],
    ]
    assert len(payload["receipts"]) == len(set(payload["receipts"])) == 2


def test_risk_v2_example_uses_only_public_protocol_core_surfaces() -> None:
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


def test_risk_v2_manifest_passes_protocol_v3_wire_validation(
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
