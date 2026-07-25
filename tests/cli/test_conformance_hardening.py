from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_source_conformance_cli_is_cwd_independent(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pheroos.cli.main", "source-conformance", str(ROOT)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["ok"] is True
    assert payload["profile"] == "pheroos-source-v3"


def test_source_conformance_cli_missing_surface_is_structured_failure(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pheroos.cli.main", "source-conformance", str(tmp_path)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert payload["ok"] is False
    assert payload["profile"] == "pheroos-source-v3"
    assert "Traceback" not in completed.stderr


def test_invalid_manifest_cli_returns_structured_json_and_nonzero_exit(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "capability.json"
    manifest_path.write_text('{"id": "invalid", "name": NaN}', encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "pheroos.cli.main", "validate", str(manifest_path)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert payload["ok"] is False
    assert "Traceback" not in completed.stderr


def test_installed_console_script_and_public_imports_are_cwd_independent(
    tmp_path: Path,
) -> None:
    console_script = Path(sys.executable).parent / "pheroos"
    completed = subprocess.run(
        [
            str(console_script),
            "validate",
            str(ROOT / "examples/toy-protocol/capability.json"),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pheroos.governance import evaluate_hybrid_collective_step; "
                "from pheroos.protocol import PheromoneKindProfile; "
                "from pheroos.trace import TraceEvent"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["ok"] is True
    assert imported.returncode == 0, imported.stderr
