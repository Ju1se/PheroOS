from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

import pheroos.conformance.schema_catalog as catalog
from scripts.generate_schema_artifacts import _write_blockers


ROOT = Path(__file__).resolve().parents[2]


def test_catalog_is_the_exact_schema_directory_owner() -> None:
    expected = {spec.path for spec in catalog.SCHEMA_ARTIFACT_SPECS}
    observed = {
        path.relative_to(ROOT).as_posix() for path in (ROOT / "schemas").glob("*.json")
    }

    assert len(catalog.SCHEMA_ARTIFACT_SPECS) == 21
    assert len(catalog.schema_surface_names()) == 25
    assert expected == observed
    assert catalog.schema_catalog_problems(ROOT) == ()


def test_every_artifact_has_one_id_alias_set_and_exact_factory_bytes() -> None:
    paths: set[str] = set()
    ids: set[str] = set()
    aliases: set[str] = set()
    for spec in catalog.SCHEMA_ARTIFACT_SPECS:
        assert spec.path not in paths
        assert spec.schema_id not in ids
        paths.add(spec.path)
        ids.add(spec.schema_id)
        assert spec.schema_version
        document = spec.factory()
        assert document["$schema"] == catalog.SCHEMA_DRAFT_2020_12
        assert document["$id"] == spec.schema_id
        assert catalog.render_schema_artifact(spec) == (ROOT / spec.path).read_bytes()
        assert json.loads(catalog.render_schema_artifact(spec)) == document
        assert sum(item.name == spec.surface for item in spec.cli_surfaces) == 1
        for surface in spec.cli_surfaces:
            assert surface.name not in aliases
            aliases.add(surface.name)
            assert catalog.schema_spec_for_surface(surface.name) is spec


def test_reader_validator_frozen_and_package_metadata_are_total() -> None:
    frozen = {
        "capability-v1",
        "capability-v2",
        "protocol-v1",
        "protocol-v2",
        "driver-v1",
        "kernel-v1",
        "scoped-trace",
    }
    for spec in catalog.SCHEMA_ARTIFACT_SPECS:
        assert (spec.typed_reader is None) is (
            spec.typed_reader_not_applicable_reason is not None
        )
        assert (spec.semantic_validator is None) is (
            spec.semantic_validator_not_applicable_reason is not None
        )
        assert spec.frozen is (spec.surface in frozen)
        assert spec.frozen is (spec.frozen_sha256 is not None)
        if spec.frozen:
            assert sha256((ROOT / spec.path).read_bytes()).hexdigest() == (
                spec.frozen_sha256
            )
        assert not spec.package_data_required
        assert spec.package_resource_path is None


def test_catalog_detects_duplicate_id_alias_and_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second, *rest = catalog.SCHEMA_ARTIFACT_SPECS
    duplicate = replace(
        second,
        path=first.path,
        schema_id=first.schema_id,
        cli_surfaces=first.cli_surfaces,
    )
    monkeypatch.setattr(
        catalog,
        "SCHEMA_ARTIFACT_SPECS",
        (first, duplicate, *rest),
    )

    problems = catalog.schema_catalog_problems(ROOT)

    assert f"duplicate_path:{first.path}" in problems
    assert f"duplicate_schema_id:{first.schema_id}" in problems
    assert any(item.startswith("duplicate_cli_surface:") for item in problems)


def test_generator_check_is_repeatable_and_side_effect_free() -> None:
    command = [
        sys.executable,
        "scripts/generate_schema_artifacts.py",
        "--check",
    ]
    first = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert first.stdout == second.stdout
    assert "verified 21 cataloged schema artifacts" in first.stdout


def test_generator_write_gate_never_treats_frozen_drift_as_writeable() -> None:
    assert _write_blockers(("bytes:capability-v1",)) == ("bytes:capability-v1",)
    assert _write_blockers(("missing:schemas/capability.schema.json",)) == (
        "missing:schemas/capability.schema.json",
    )
    assert _write_blockers(("bytes:runtime-scope-v1",)) == ()


def test_core_packages_do_not_reverse_import_the_catalog() -> None:
    forbidden = "pheroos.conformance.schema_catalog"
    for package in ("protocol", "kernel", "drivers", "governance", "trace"):
        for path in (ROOT / "pheroos" / package).rglob("*.py"):
            assert forbidden not in path.read_text(encoding="utf-8"), path
