from __future__ import annotations

import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from typing import Any
import unicodedata

from pheroos.conformance.runtime_compatibility import (
    RuntimeCompatibilityDiagnosticCodeV1,
    build_runtime_compatibility_manifest_v1,
    create_runtime_compatibility_claim_v1,
    evaluate_runtime_compatibility_v1,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "pheroos/conformance/abi/runtime-compatibility-v1.json"
ROOT_PREFIX = b"pheroos-runtime-compatibility-manifest-v1\x00"


def _independent_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        assert key not in result
        assert key and key == key.strip() and "\x00" not in key
        assert unicodedata.normalize("NFC", key) == key
        result[key] = value
    return result


def _independent_parse(data: bytes) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise AssertionError(f"non-finite JSON value: {value}")

    payload = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_independent_pairs,
        parse_constant=reject_constant,
    )
    assert type(payload) is dict
    assert set(payload) == {
        "manifest_version",
        "manifest_root",
        "required_profile",
        "optional_profiles",
        "optional_capabilities",
    }
    return payload


def _independent_root(payload: dict[str, Any]) -> str:
    projection = dict(payload)
    observed = projection.pop("manifest_root")
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    calculated = "sha256:" + sha256(ROOT_PREFIX + canonical).hexdigest()
    assert observed == calculated
    return calculated


def test_independent_parser_and_vector_match_the_checked_manifest() -> None:
    payload = _independent_parse(ARTIFACT.read_bytes())
    assert _independent_root(payload) == payload["manifest_root"]
    required = payload["required_profile"]["requirements"]
    assert [item["component_id"] for item in required] == sorted(
        item["component_id"] for item in required
    )
    assert [item["profile_id"] for item in payload["optional_profiles"]] == sorted(
        item["profile_id"] for item in payload["optional_profiles"]
    )
    assert [
        item["capability_id"] for item in payload["optional_capabilities"]
    ] == sorted(item["capability_id"] for item in payload["optional_capabilities"])

    versions = {item["component_id"]: item["version_id"] for item in required}
    exact = create_runtime_compatibility_claim_v1(versions)
    assert evaluate_runtime_compatibility_v1(
        build_runtime_compatibility_manifest_v1(), exact
    ).ok

    versions["kernel.plan"] = "pheroos-kernel-plan-v999"
    mismatch = create_runtime_compatibility_claim_v1(versions)
    report = evaluate_runtime_compatibility_v1(
        build_runtime_compatibility_manifest_v1(), mismatch
    )
    assert [(item.code, item.subject) for item in report.diagnostics] == [
        (RuntimeCompatibilityDiagnosticCodeV1.VERSION_MISMATCH, "kernel.plan")
    ]


def test_artifact_is_package_data_and_loads_from_an_external_cwd(
    tmp_path: Path,
) -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    assert (
        "abi/*.json"
        in configuration["tool"]["setuptools"]["package-data"]["pheroos.conformance"]
    )

    site_packages = tmp_path / "site-packages"
    shutil.copytree(
        ROOT / "pheroos",
        site_packages / "pheroos",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    external_cwd = tmp_path / "external-cwd"
    external_cwd.mkdir()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(site_packages)
    completed = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            (
                "from pheroos.conformance.runtime_compatibility import "
                "load_runtime_compatibility_manifest_v1 as load; "
                "item = load(); "
                "print(item.manifest_root, len(item.required_profile.requirements))"
            ),
        ],
        cwd=external_cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    source_payload = _independent_parse(ARTIFACT.read_bytes())
    required_count = len(source_payload["required_profile"]["requirements"])
    assert completed.stdout.strip() == (
        f"{source_payload['manifest_root']} {required_count}"
    )


def test_compatibility_composition_has_no_reverse_core_import() -> None:
    for package in ("protocol", "kernel", "drivers", "governance", "trace"):
        for path in (ROOT / "pheroos" / package).rglob("*.py"):
            tree = ast.parse(path.read_text("utf-8"))
            imports = {
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            }
            imports.update(
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
            assert not any(
                name.startswith("pheroos.conformance.runtime_compatibility")
                or name.startswith("pheroos.conformance._runtime_compatibility")
                for name in imports
            ), path
