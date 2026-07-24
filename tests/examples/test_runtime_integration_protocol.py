from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_runtime_integration_example_passes_from_external_cwd(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "examples" / "runtime-integration-protocol" / "run.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload == {
        "name": "runtime_integration_v1_contract",
        "ok": True,
        "detail": "",
    }


def test_runtime_integration_example_uses_only_public_package_facades() -> None:
    root = Path(__file__).resolve().parents[2]
    directory = root / "examples" / "runtime-integration-protocol"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (directory / "run.py", directory / "stores.py")
    )
    assert "pheroos.conformance._" not in source
    assert "pheroos.drivers._" not in source
    assert "pheroos.governance._" not in source
    assert "pheroos.kernel._" not in source
    assert "pheroos.protocol._" not in source
    assert "pheroos.trace._" not in source
    assert "InMemoryDriverInvocationStoreV2" not in source
    assert "InMemoryScopedTraceStoreV2" not in source
