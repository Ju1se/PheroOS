from __future__ import annotations

from importlib import import_module
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from typing import Any

from pheroos.conformance.public_api_inventory import (
    PUBLIC_API_INVENTORY_PATH,
    PUBLIC_PACKAGES,
    _class_member_shapes,
    build_public_api_inventory,
    load_public_api_inventory,
)


ROOT = Path(__file__).resolve().parents[1]


class _SyntheticMemberSurface:
    @property
    def label(self) -> str:
        return "synthetic"

    @label.setter
    def label(self, value: str) -> None:
        del value

    @classmethod
    def create(cls, name: str = "synthetic") -> _SyntheticMemberSurface:
        del name
        return cls()

    @staticmethod
    def normalize(value: int = 0) -> int:
        return value

    @classmethod
    async def create_async(cls, name: str) -> _SyntheticMemberSurface:
        del name
        return cls()

    @staticmethod
    async def normalize_async(value: int) -> int:
        return value

    async def fetch(self, resource: str, *, limit: int = 1) -> bool:
        del resource, limit
        return True


def _exports(inventory: dict[str, Any], package: str) -> dict[str, dict[str, Any]]:
    packages = inventory["packages"]
    assert isinstance(packages, dict)
    package_shape = packages[package]
    assert isinstance(package_shape, dict)
    exports = package_shape["exports"]
    assert isinstance(exports, list)
    return {item["name"]: item for item in exports}


def test_checked_public_api_inventory_matches_runtime_shapes() -> None:
    expected = load_public_api_inventory(ROOT)

    assert expected == build_public_api_inventory()


def test_inventory_covers_every_declared_export_in_the_six_public_packages() -> None:
    inventory = build_public_api_inventory()

    assert tuple(inventory["packages"]) == PUBLIC_PACKAGES
    for package_name in PUBLIC_PACKAGES:
        module = import_module(package_name)
        exports = _exports(inventory, package_name)
        assert set(exports) == set(module.__all__)
        assert all(
            export["kind"] == "constant" or export["signature"] is not None
            for export in exports.values()
        )


def test_inventory_records_signature_dataclass_enum_constant_and_alias_shapes() -> None:
    inventory = build_public_api_inventory()
    protocol_exports = _exports(inventory, "pheroos.protocol")

    validate_ok = protocol_exports["validate_ok"]
    assert validate_ok["kind"] == "function"
    assert validate_ok["owner"] == "pheroos.protocol.validation"
    assert validate_ok["signature"] == {
        "parameters": [
            {
                "annotation": "CapabilityManifest",
                "default": {"kind": "missing"},
                "kind": "POSITIONAL_OR_KEYWORD",
                "name": "manifest",
                "required": True,
            }
        ],
        "return": "bool",
    }

    policy = protocol_exports["CollectiveDecisionPolicy"]
    assert policy["kind"] == "dataclass"
    dataclass_shape = policy["dataclass"]
    assert dataclass_shape["frozen"] is True
    assert dataclass_shape["kw_only"] is False
    mode = dataclass_shape["fields"][0]
    assert mode == {
        "annotation": "str",
        "default": {"kind": "value", "value": "quorum"},
        "init": True,
        "kw_only": False,
        "name": "mode",
    }
    kind_profiles = next(
        field
        for field in dataclass_shape["fields"]
        if field["name"] == "pheromone_kind_profiles"
    )
    assert kind_profiles["default"] == {
        "factory": "builtins:dict",
        "kind": "factory",
    }

    assurance = protocol_exports["CommitAssurance"]
    assert assurance["kind"] == "enum"
    assert [member["name"] for member in assurance["enum"]["members"]] == [
        "ADVISORY",
        "EVIDENCE_BOUND",
        "CERTIFIED",
        "DISTRIBUTED",
    ]
    assert assurance["enum"]["members"][0] == {
        "canonical_name": "ADVISORY",
        "name": "ADVISORY",
        "value": "advisory",
    }

    collective_modes = protocol_exports["SWARM_COLLECTIVE_MODES"]
    assert collective_modes["kind"] == "constant"
    assert collective_modes["constant"] == {
        "type": "builtins:frozenset",
        "value": {
            "items": ["ant_colony", "bee_swarm", "hybrid"],
            "kind": "frozenset",
        },
    }

    expected_assurance_aliases = [
        "pheroos.governance.CommitAssurance",
        "pheroos.protocol.CommitAssurance",
    ]
    governance_exports = _exports(inventory, "pheroos.governance")
    governance_commit_version = governance_exports["COMMIT_CANONICAL_VERSION"]
    assert governance_commit_version["owner"] == "pheroos.protocol.commit_models"
    assert governance_commit_version["attribute"] == "COMMIT_CANONICAL_VERSION"
    assert governance_commit_version["binding_owner"] == (
        "pheroos.governance.commit_numeric"
    )
    assert assurance["aliases"] == expected_assurance_aliases
    assert (
        governance_exports["CommitAssurance"]["aliases"]
        == expected_assurance_aliases
    )
    expected_trace_aliases = [
        "pheroos.governance.TraceEvent",
        "pheroos.trace.TraceEvent",
    ]
    trace_exports = _exports(inventory, "pheroos.trace")
    assert governance_exports["TraceEvent"]["aliases"] == expected_trace_aliases
    assert trace_exports["TraceEvent"]["aliases"] == expected_trace_aliases

    driver_exports = _exports(inventory, "pheroos.drivers")
    registry_members = {
        member["name"]: member
        for member in driver_exports["DriverRegistry"]["members"]
    }
    assert set(registry_members) == {"descriptors", "get", "register"}
    assert registry_members["descriptors"]["getter_signature"] == {
        "parameters": [],
        "return": "Mapping[str, DriverDescriptor]",
    }
    assert registry_members["descriptors"]["setter_present"] is False
    assert registry_members["get"]["signature"]["parameters"][0] == {
        "annotation": "str",
        "default": {"kind": "missing"},
        "kind": "POSITIONAL_OR_KEYWORD",
        "name": "driver_id",
        "required": True,
    }


def test_class_member_inventory_distinguishes_descriptor_and_async_kinds() -> None:
    members = {
        member["name"]: member
        for member in _class_member_shapes(_SyntheticMemberSurface)
    }

    assert members["create"]["kind"] == "classmethod"
    assert members["create"]["signature"] == {
        "parameters": [
            {
                "annotation": "str",
                "default": {"kind": "value", "value": "synthetic"},
                "kind": "POSITIONAL_OR_KEYWORD",
                "name": "name",
                "required": False,
            }
        ],
        "return": "_SyntheticMemberSurface",
    }
    assert members["normalize"]["kind"] == "staticmethod"
    assert members["create_async"]["kind"] == "async_classmethod"
    assert members["normalize_async"]["kind"] == "async_staticmethod"
    assert members["fetch"]["kind"] == "async_method"
    assert members["fetch"]["signature"]["parameters"][1]["kind"] == (
        "KEYWORD_ONLY"
    )
    assert members["label"]["kind"] == "property"
    assert members["label"]["getter_present"] is True
    assert members["label"]["getter_signature"] == {
        "parameters": [],
        "return": "str",
    }
    assert members["label"]["setter_present"] is True
    assert members["label"]["setter_signature"] == {
        "parameters": [
            {
                "annotation": "str",
                "default": {"kind": "missing"},
                "kind": "POSITIONAL_OR_KEYWORD",
                "name": "value",
                "required": True,
            }
        ],
        "return": "None",
    }


def test_public_api_inventory_generator_check_mode_accepts_checked_artifact() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/generate_public_api_inventory.py", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_inventory_is_canonical_package_data_and_external_cwd_safe(
    tmp_path: Path,
) -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    package_data = configuration["tool"]["setuptools"]["package-data"]
    assert "abi/*.json" in package_data["pheroos.conformance"]
    assert PUBLIC_API_INVENTORY_PATH.parts[:3] == (
        "pheroos",
        "conformance",
        "abi",
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
                "from pheroos.conformance import run_source_conformance; "
                "report = run_source_conformance(); "
                "assert report.ok, report.to_dict()"
            ),
        ],
        cwd=external_cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
