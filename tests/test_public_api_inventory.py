from __future__ import annotations

from collections.abc import Sequence
from importlib import import_module
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tomllib
from typing import Any, overload

from pheroos.conformance.public_api_inventory import (
    PUBLIC_API_INVENTORY_PATH,
    PUBLIC_PACKAGES,
    _annotation_shape,
    _callable_identity,
    _class_member_shapes,
    _signature_shape,
    _source_binding_origins,
    _static_binding_origins,
    _type_identity,
    _value_shape,
    build_public_api_inventory,
    load_public_api_inventory,
    public_api_inventory_differences,
    render_public_api_inventory,
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


class _SyntheticSequence(Sequence[int]):
    def __init__(self, *items: int) -> None:
        self._items = items

    @overload
    def __getitem__(self, index: int) -> int: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[int]: ...

    def __getitem__(self, index: int | slice) -> int | Sequence[int]:
        return self._items[index]

    def __len__(self) -> int:
        return len(self._items)


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
                "annotation": "CapabilityManifest | ScopedCapabilityManifestV2",
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
        governance_exports["CommitAssurance"]["aliases"] == expected_assurance_aliases
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
        member["name"]: member for member in driver_exports["DriverRegistry"]["members"]
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
    assert members["fetch"]["signature"]["parameters"][1]["kind"] == ("KEYWORD_ONLY")
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


def test_path_type_identity_ignores_python_313_private_storage_module() -> None:
    private_path_type = type(
        "PosixPath",
        (PurePosixPath,),
        {"__module__": "pathlib._local"},
    )
    unrelated_private_type = type(
        "Opaque",
        (),
        {"__module__": "pathlib._local"},
    )

    assert _type_identity(private_path_type) == "pathlib:PosixPath"
    assert _type_identity(unrelated_private_type) == "pathlib._local:Opaque"
    assert _type_identity(type(Path())) == f"pathlib:{type(Path()).__qualname__}"
    assert _type_identity(PurePosixPath) == "pathlib:PurePosixPath"


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


def test_inventory_render_load_and_difference_limits_fail_closed(
    tmp_path: Path,
) -> None:
    inventory = build_public_api_inventory()
    rendered = render_public_api_inventory(inventory)
    artifact = tmp_path / PUBLIC_API_INVENTORY_PATH
    artifact.parent.mkdir(parents=True)
    artifact.write_text(rendered, encoding="utf-8")

    assert rendered.endswith("\n")
    assert load_public_api_inventory(tmp_path) == inventory
    assert public_api_inventory_differences({"a": 1}, {"a": 2}, limit=0) == []
    assert public_api_inventory_differences({"a": 1, "b": 2}, {}, limit=1) == ["$.a"]
    assert public_api_inventory_differences([1, 2], [], limit=1) == ["$.length"]
    assert public_api_inventory_differences([1, 2], [3, 4], limit=1) == ["$[0]"]
    assert public_api_inventory_differences(
        {"exports": [{"name": "one"}, {"name": "two"}]},
        {"exports": []},
        limit=1,
    ) == ["$.exports[one]"]

    artifact.write_text("[]", encoding="utf-8")
    try:
        load_public_api_inventory(tmp_path)
    except ValueError as exc:
        assert str(exc) == "public API inventory must be a JSON object"
    else:
        raise AssertionError("a non-object public API inventory must fail closed")


def test_inventory_static_and_source_origin_parsing_is_explicit(tmp_path: Path) -> None:
    assert _static_binding_origins(
        "synthetic.package",
        {"Alias": ("owner.module", "Target")},
    ) == {"Alias": ("owner.module", "Target", False)}
    for malformed in (
        {1: ("owner.module", "Target")},
        {"Alias": "owner.module.Target"},
        {"Alias": ("owner.module",)},
        {"Alias": ("owner.module", 7)},
    ):
        try:
            _static_binding_origins("synthetic.package", malformed)
        except ValueError as exc:
            assert "malformed static public API mapping" in str(exc)
        else:
            raise AssertionError("a malformed static public API mapping must fail")

    source = tmp_path / "surface.py"
    source.write_text(
        "\n".join(
            (
                "from .child import Thing as ImportedThing",
                "from .wildcard import *",
                "import json as codec",
                "import os.path",
                "alias = ImportedThing",
                "encoder = codec.dumps",
                "first, (second, third) = values",
                "annotated: object = encoder",
                "holder.value = encoder",
                "def operation(value): return value",
                "async def async_operation(value): return value",
                "class Record: pass",
            )
        ),
        encoding="utf-8",
    )

    origins = _source_binding_origins("synthetic.package", source)

    assert origins["ImportedThing"] == (
        "synthetic.package.child",
        "Thing",
        False,
    )
    assert origins["alias"] == ("synthetic.package", "ImportedThing", False)
    assert origins["encoder"] == ("json", "dumps", False)
    assert origins["first"] == ("synthetic.package", "values", False)
    assert origins["second"] == ("synthetic.package", "values", False)
    assert origins["third"] == ("synthetic.package", "values", False)
    assert origins["annotated"] == ("synthetic.package", "encoder", False)
    assert origins["operation"] == ("synthetic.package", "operation", True)
    assert origins["async_operation"] == (
        "synthetic.package",
        "async_operation",
        True,
    )
    assert origins["Record"] == ("synthetic.package", "Record", True)


def test_inventory_signature_and_annotation_fallbacks_are_deterministic() -> None:
    assert _signature_shape(object()) is None
    fallback = _signature_shape(dict)
    assert fallback is not None
    assert fallback["fallback_source"] == "__init__"
    assert all(parameter["name"] != "self" for parameter in fallback["parameters"])

    def invalid_signature(self: object) -> None:
        del self

    invalid_signature.__signature__ = "invalid"  # type: ignore[attr-defined]
    no_signature = type(
        "NoSignature",
        (),
        {"__signature__": "invalid", "__init__": invalid_signature},
    )
    assert _signature_shape(no_signature) is None

    annotation = type("Annotation", (), {})()
    annotation.__module__ = "synthetic"  # type: ignore[attr-defined]
    annotation.__qualname__ = "Annotation"  # type: ignore[attr-defined]
    assert _annotation_shape(annotation) == "synthetic:Annotation"
    assert _annotation_shape(42) == "42"

    try:
        _callable_identity(object())
    except TypeError as exc:
        assert "unsupported public ABI factory type" in str(exc)
    else:
        raise AssertionError("an anonymous default factory must fail closed")


def test_inventory_value_projection_handles_all_portable_values_and_cycles() -> None:
    assert _value_shape(float("nan")) == {"kind": "float", "value": "nan"}
    assert _value_shape(float("inf")) == {"kind": "float", "value": "inf"}
    assert _value_shape(float("-inf")) == {"kind": "float", "value": "-inf"}
    assert _value_shape(b"\x00\xff") == {"hex": "00ff", "kind": "bytes"}
    assert _value_shape(complex(1, -2)) == {
        "imaginary": -2.0,
        "kind": "complex",
        "real": 1.0,
    }
    assert _value_shape(Ellipsis) == {"kind": "ellipsis"}
    assert _value_shape(NotImplemented) == {"kind": "not-implemented"}
    assert _value_shape(Path("/tmp/example.txt")) == {
        "kind": "path",
        "value": "example.txt",
    }
    assert _value_shape(range(1, 7, 2)) == {
        "kind": "range",
        "start": 1,
        "step": 2,
        "stop": 7,
    }
    assert _value_shape(math.isfinite)["kind"] == "object-reference"
    assert _value_shape([1, "two"]) == {"items": [1, "two"], "kind": "list"}
    assert _value_shape(_SyntheticSequence(1, 2)) == {
        "items": [1, 2],
        "kind": "sequence",
        "type": f"{__name__}:_SyntheticSequence",
    }

    cyclic: list[object] = []
    cyclic.append(cyclic)
    try:
        _value_shape(cyclic)
    except TypeError as exc:
        assert "cyclic public ABI value is unsupported" in str(exc)
    else:
        raise AssertionError("a cyclic public ABI value must fail closed")

    try:
        _value_shape(object())
    except TypeError as exc:
        assert "unsupported public ABI value type" in str(exc)
    else:
        raise AssertionError("an opaque public ABI value must fail closed")
