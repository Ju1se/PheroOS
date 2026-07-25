from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from pheroos.cli.main import SCHEMA_SURFACES, WIRE_SURFACES, main
from pheroos.conformance.schema_catalog import (
    SCHEMA_ARTIFACT_SPECS,
    schema_spec_for_surface,
    schema_surface_names,
)


ROOT = Path(__file__).resolve().parents[2]


def _invoke(capsys: Any, *arguments: str) -> tuple[int, bytes]:
    code = main(list(arguments))
    return code, capsys.readouterr().out.encode("utf-8")


def test_cli_schema_and_wire_surfaces_are_catalog_derived() -> None:
    expected = schema_surface_names()

    assert SCHEMA_SURFACES == expected
    assert WIRE_SURFACES == expected
    assert len(expected) == len(set(expected))


@pytest.mark.parametrize("surface", schema_surface_names())
def test_every_cli_export_is_the_exact_checked_artifact(
    surface: str,
    capsys: Any,
) -> None:
    code, output = _invoke(capsys, "schema", "export", surface)
    spec = schema_spec_for_surface(surface)

    assert code == 0
    assert output == (ROOT / spec.path).read_bytes()


def test_schema_list_reports_file_hash_state_and_canonical_surface(
    capsys: Any,
) -> None:
    code, output = _invoke(capsys, "schema", "list")
    payload = json.loads(output)
    entries = {item["surface"]: item for item in payload["schemas"]}

    assert code == 0
    assert tuple(entries) == schema_surface_names()
    for surface, entry in entries.items():
        spec = schema_spec_for_surface(surface)
        artifact = (ROOT / spec.path).read_bytes()
        assert entry["canonical_surface"] == spec.surface
        assert entry["path"] == spec.path
        assert entry["artifact_state"] == ("frozen" if spec.frozen else "writeable")
        assert entry["sha256"] == "sha256:" + sha256(artifact).hexdigest()


def test_external_cwd_schema_export_matches_checked_bytes(tmp_path: Path) -> None:
    spec = next(
        item for item in SCHEMA_ARTIFACT_SPECS if item.surface == "scoped-trace"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pheroos.cli.main",
            "schema",
            "export",
            spec.surface,
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
    )

    assert completed.stdout == (ROOT / spec.path).read_bytes()
