"""Deterministic inventory of the supported Python package ABI.

This module is intentionally internal to :mod:`pheroos.conformance`.  It
describes existing public bindings without creating another public binding of
its own.  The checked JSON artifact lets source conformance detect shape drift
that a names-only ``__all__`` snapshot cannot see.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence, Set
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from functools import cache
from importlib import import_module
from importlib.util import resolve_name
import inspect
import json
from math import isfinite
from pathlib import Path, PurePath
from types import MappingProxyType
from typing import Any


PUBLIC_API_INVENTORY_VERSION = "pheroos-public-python-api-v1"
PUBLIC_API_INVENTORY_PATH = Path(
    "pheroos/conformance/abi/public-python-api-v1.json"
)
PUBLIC_PACKAGES = (
    "pheroos.protocol",
    "pheroos.governance",
    "pheroos.kernel",
    "pheroos.drivers",
    "pheroos.trace",
    "pheroos.conformance",
)


def build_public_api_inventory() -> dict[str, Any]:
    """Return the current six-package public ABI as JSON-compatible data."""

    modules = {name: import_module(name) for name in PUBLIC_PACKAGES}
    binding_origins = {name: _module_binding_origins(name) for name in modules}
    identity_bindings: dict[int, list[str]] = {}
    for package_name, module in modules.items():
        for export_name in module.__all__:
            value = getattr(module, export_name)
            if _has_stable_identity(value):
                identity_bindings.setdefault(id(value), []).append(
                    f"{package_name}.{export_name}"
                )

    packages: dict[str, Any] = {}
    export_count = 0
    for package_name, module in modules.items():
        export_names = sorted(module.__all__)
        export_count += len(export_names)
        exports = [
            _export_shape(
                export_name,
                getattr(module, export_name),
                binding_origins[package_name].get(
                    export_name,
                    (package_name, export_name, True),
                ),
                identity_bindings,
            )
            for export_name in export_names
        ]
        packages[package_name] = {
            "export_count": len(exports),
            "exports": exports,
        }

    return {
        "artifact_version": PUBLIC_API_INVENTORY_VERSION,
        "identity_policy": "classes-and-functions-by-runtime-object-identity",
        "packages": packages,
        "summary": {
            "export_count": export_count,
            "package_count": len(PUBLIC_PACKAGES),
        },
    }


def render_public_api_inventory(inventory: Mapping[str, Any]) -> str:
    """Render an inventory with deterministic formatting and a final newline."""

    return json.dumps(
        inventory,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def load_public_api_inventory(root: str | Path) -> dict[str, Any]:
    """Load the checked inventory rooted at a source tree."""

    path = Path(root) / PUBLIC_API_INVENTORY_PATH
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("public API inventory must be a JSON object")
    return loaded


def public_api_inventory_differences(
    expected: Any,
    observed: Any,
    *,
    limit: int = 32,
) -> list[str]:
    """Return bounded structural paths whose checked and runtime shapes differ."""

    differences: list[str] = []
    _collect_differences(expected, observed, "$", differences, limit)
    return differences


def _collect_differences(
    expected: Any,
    observed: Any,
    path: str,
    differences: list[str],
    limit: int,
) -> None:
    if len(differences) >= limit:
        return
    if type(expected) is not type(observed):
        differences.append(path)
        return
    if isinstance(expected, dict):
        expected_keys = set(expected)
        observed_keys = set(observed)
        for key in sorted(expected_keys | observed_keys):
            child = f"{path}.{key}"
            if key not in expected or key not in observed:
                differences.append(child)
            else:
                _collect_differences(
                    expected[key], observed[key], child, differences, limit
                )
            if len(differences) >= limit:
                return
        return
    if isinstance(expected, list):
        if path.endswith((".exports", ".members")):
            expected_exports = _named_exports(expected)
            observed_exports = _named_exports(observed)
            if expected_exports is not None and observed_exports is not None:
                for name in sorted(set(expected_exports) | set(observed_exports)):
                    child = f"{path}[{name}]"
                    if name not in expected_exports or name not in observed_exports:
                        differences.append(child)
                    else:
                        _collect_differences(
                            expected_exports[name],
                            observed_exports[name],
                            child,
                            differences,
                            limit,
                        )
                    if len(differences) >= limit:
                        return
                return
        if len(expected) != len(observed):
            differences.append(f"{path}.length")
            if len(differences) >= limit:
                return
        for index, (expected_item, observed_item) in enumerate(
            zip(expected, observed, strict=False)
        ):
            _collect_differences(
                expected_item,
                observed_item,
                f"{path}[{index}]",
                differences,
                limit,
            )
            if len(differences) >= limit:
                return
        return
    if expected != observed:
        differences.append(path)


def _named_exports(items: list[Any]) -> dict[str, Any] | None:
    if not all(
        isinstance(item, dict) and isinstance(item.get("name"), str)
        for item in items
    ):
        return None
    named = {item["name"]: item for item in items}
    return named if len(named) == len(items) else None


@cache
def _module_binding_origins(
    package_name: str,
) -> dict[str, tuple[str, str, bool]]:
    module = import_module(package_name)
    static_public_api = module.__dict__.get("_PUBLIC_API")
    if static_public_api is not None:
        origins: dict[str, tuple[str, str, bool]] = {}
        for name, target in static_public_api.items():
            if not (
                isinstance(name, str)
                and isinstance(target, tuple)
                and len(target) == 2
                and all(isinstance(item, str) for item in target)
            ):
                raise ValueError(
                    f"{package_name} has a malformed static public API mapping"
                )
            origins[name] = (target[0], target[1], False)
        return origins
    source_path = getattr(module, "__file__", None)
    if source_path is None:
        return {}
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    origins: dict[str, tuple[str, str, bool]] = {}
    imported_modules: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            imported_module = _resolved_import_owner(node, package_name)
            for alias in node.names:
                if alias.name == "*":
                    continue
                origins[alias.asname or alias.name] = (
                    imported_module,
                    alias.name,
                    False,
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".")[0]
                imported_modules[bound_name] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            origins[node.name] = (package_name, node.name, True)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            assigned_value = node.value
            for target in targets:
                for name in _assigned_names(target):
                    origins[name] = _assigned_origin(
                        package_name,
                        name,
                        assigned_value,
                        imported_modules,
                    )
    return origins


def _assigned_origin(
    package_name: str,
    assigned_name: str,
    value: ast.expr | None,
    imported_modules: Mapping[str, str],
) -> tuple[str, str, bool]:
    if isinstance(value, ast.Name):
        return (package_name, value.id, False)
    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
        imported_module = imported_modules.get(value.value.id)
        if imported_module is not None:
            return (imported_module, value.attr, False)
    return (package_name, assigned_name, True)


def _resolved_import_owner(node: ast.ImportFrom, package_name: str) -> str:
    module_name = node.module or ""
    if node.level:
        return resolve_name(f"{'.' * node.level}{module_name}", package_name)
    return module_name


def _assigned_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in _assigned_names(item)]
    return []


def _export_shape(
    export_name: str,
    value: Any,
    binding_origin: tuple[str, str, bool],
    identity_bindings: Mapping[int, list[str]],
) -> dict[str, Any]:
    kind = _public_kind(value)
    stable_identity = _identity(value) if _has_stable_identity(value) else None
    binding_owner, binding_attribute, _ = binding_origin
    if stable_identity is not None:
        owner = getattr(value, "__module__", binding_owner)
        attribute = getattr(value, "__qualname__", binding_attribute)
    else:
        owner, attribute = _canonical_constant_origin(
            binding_owner,
            binding_attribute,
        )
    shape: dict[str, Any] = {
        "aliases": _aliases_for(value, stable_identity, identity_bindings),
        "attribute": attribute,
        "binding_owner": binding_owner,
        "identity": stable_identity,
        "kind": kind,
        "name": export_name,
        "owner": owner,
    }
    if kind in {"class", "dataclass", "enum", "function"}:
        shape["signature"] = _signature_shape(value)
    else:
        shape["signature"] = None
    if inspect.isclass(value):
        shape["members"] = _class_member_shapes(value)
    if kind == "dataclass":
        shape["dataclass"] = _dataclass_shape(value)
    if kind == "enum":
        shape["enum"] = _enum_shape(value)
    if kind == "constant":
        shape["constant"] = {
            "type": _type_identity(type(value)),
            "value": _value_shape(value),
        }
    return shape


def _canonical_constant_origin(
    module_name: str,
    attribute: str,
    visited: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[str, str]:
    marker = (module_name, attribute)
    if marker in visited:
        return marker
    origin = _module_binding_origins(module_name).get(attribute)
    if origin is None:
        return marker
    origin_module, origin_attribute, direct = origin
    if direct:
        return origin_module, origin_attribute
    return _canonical_constant_origin(
        origin_module,
        origin_attribute,
        visited | {marker},
    )


def _public_kind(value: Any) -> str:
    if inspect.isclass(value) and issubclass(value, Enum):
        return "enum"
    if inspect.isclass(value) and is_dataclass(value):
        return "dataclass"
    if inspect.isclass(value):
        return "class"
    if inspect.isroutine(value):
        return "function"
    return "constant"


def _has_stable_identity(value: Any) -> bool:
    return inspect.isclass(value) or inspect.isroutine(value)


def _identity(value: Any) -> str:
    return f"{value.__module__}:{value.__qualname__}"


def _aliases_for(
    value: Any,
    stable_identity: str | None,
    identity_bindings: Mapping[int, list[str]],
) -> list[str]:
    if stable_identity is None:
        return []
    bindings = sorted(identity_bindings.get(id(value), []))
    return bindings if len(bindings) > 1 else []


def _type_identity(value: type[Any]) -> str:
    return f"{value.__module__}:{value.__qualname__}"


def _class_member_shapes(value: type[Any]) -> list[dict[str, Any]]:
    """Describe direct public methods/properties without binding descriptors."""

    dataclass_field_names = (
        {field.name for field in fields(value)} if is_dataclass(value) else set()
    )
    members: list[dict[str, Any]] = []
    for name, descriptor in sorted(value.__dict__.items()):
        if name.startswith("_") or name in dataclass_field_names:
            continue
        if isinstance(descriptor, property):
            members.append(_property_shape(name, descriptor))
            continue
        if isinstance(descriptor, staticmethod):
            function = descriptor.__func__
            members.append(_method_shape(name, function, "staticmethod", False))
            continue
        if isinstance(descriptor, classmethod):
            function = descriptor.__func__
            members.append(_method_shape(name, function, "classmethod", True))
            continue
        if inspect.isfunction(descriptor):
            members.append(_method_shape(name, descriptor, "method", True))
    return members


def _method_shape(
    name: str,
    function: Any,
    kind: str,
    drop_first: bool,
) -> dict[str, Any]:
    if inspect.iscoroutinefunction(function) or inspect.isasyncgenfunction(function):
        kind = f"async_{kind}"
    return {
        "abstract": bool(getattr(function, "__isabstractmethod__", False)),
        "kind": kind,
        "name": name,
        "signature": _signature_shape(function, drop_first=drop_first),
    }


def _property_shape(name: str, descriptor: property) -> dict[str, Any]:
    getter = descriptor.fget
    setter = descriptor.fset
    return {
        "abstract": bool(getattr(descriptor, "__isabstractmethod__", False)),
        "deleter_present": descriptor.fdel is not None,
        "getter_async": getter is not None
        and (
            inspect.iscoroutinefunction(getter)
            or inspect.isasyncgenfunction(getter)
        ),
        "getter_present": getter is not None,
        "getter_signature": _signature_shape(getter, drop_first=True)
        if getter is not None
        else None,
        "kind": "property",
        "name": name,
        "setter_async": setter is not None
        and (
            inspect.iscoroutinefunction(setter)
            or inspect.isasyncgenfunction(setter)
        ),
        "setter_present": setter is not None,
        "setter_signature": _signature_shape(setter, drop_first=True)
        if setter is not None
        else None,
    }


def _signature_shape(
    value: Any,
    *,
    drop_first: bool = False,
) -> dict[str, Any] | None:
    fallback_source: str | None = None
    try:
        signature = inspect.signature(value, eval_str=False)
    except (TypeError, ValueError):
        if not inspect.isclass(value):
            return None
        try:
            signature = inspect.signature(value.__init__, eval_str=False)
        except (TypeError, ValueError):
            return None
        fallback_source = "__init__"
    signature_parameters = list(signature.parameters.values())
    if (fallback_source is not None or drop_first) and signature_parameters:
        first = signature_parameters[0]
        if drop_first or first.name in {"self", "cls"}:
            signature_parameters = signature_parameters[1:]
    parameters = []
    for parameter in signature_parameters:
        parameters.append(
            {
                "annotation": _annotation_shape(parameter.annotation),
                "default": _parameter_default_shape(parameter.default),
                "kind": parameter.kind.name,
                "name": parameter.name,
                "required": parameter.default is inspect.Parameter.empty
                and parameter.kind
                not in {
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                },
            }
        )
    shape = {
        "parameters": parameters,
        "return": _annotation_shape(signature.return_annotation),
    }
    if fallback_source is not None:
        shape["fallback_source"] = fallback_source
    return shape


def _parameter_default_shape(value: Any) -> dict[str, Any]:
    if value is inspect.Parameter.empty:
        return {"kind": "missing"}
    if _type_identity(type(value)) == "dataclasses:_HAS_DEFAULT_FACTORY_CLASS":
        return {"kind": "dataclass-factory"}
    return {"kind": "value", "value": _value_shape(value)}


def _annotation_shape(annotation: Any) -> str | None:
    if annotation is inspect.Signature.empty:
        return None
    if isinstance(annotation, str):
        return annotation
    if annotation is None:
        return "None"
    if inspect.isclass(annotation):
        return _type_identity(annotation)
    module_name = getattr(annotation, "__module__", None)
    qualified_name = getattr(annotation, "__qualname__", None)
    if module_name and qualified_name:
        return f"{module_name}:{qualified_name}"
    return inspect.formatannotation(annotation)


def _dataclass_shape(value: type[Any]) -> dict[str, Any]:
    parameters = value.__dataclass_params__
    return {
        "fields": [
            {
                "annotation": _annotation_shape(field.type),
                "default": _field_default_shape(field),
                "init": field.init,
                "kw_only": field.kw_only,
                "name": field.name,
            }
            for field in fields(value)
        ],
        "frozen": parameters.frozen,
        "kw_only": getattr(parameters, "kw_only", False),
    }


def _field_default_shape(field: Any) -> dict[str, Any]:
    if field.default is not MISSING:
        return {"kind": "value", "value": _value_shape(field.default)}
    if field.default_factory is not MISSING:
        return {
            "factory": _callable_identity(field.default_factory),
            "kind": "factory",
        }
    return {"kind": "missing"}


def _enum_shape(value: type[Enum]) -> dict[str, Any]:
    return {
        "members": [
            {
                "canonical_name": member.name,
                "name": name,
                "value": _value_shape(member.value),
            }
            for name, member in value.__members__.items()
        ]
    }


def _callable_identity(value: Any) -> str:
    module_name = getattr(value, "__module__", None)
    qualified_name = getattr(value, "__qualname__", None)
    if module_name and qualified_name:
        return f"{module_name}:{qualified_name}"
    raise TypeError(
        f"unsupported public ABI factory type: {_type_identity(type(value))}"
    )


def _value_shape(value: Any, active: set[int] | None = None) -> Any:
    if isinstance(value, Enum):
        return {
            "kind": "enum-member",
            "member": value.name,
            "type": _type_identity(type(value)),
            "value": _value_shape(value.value, active),
        }
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if isfinite(value):
            return value
        return {
            "kind": "float",
            "value": "nan" if value != value else ("inf" if value > 0 else "-inf"),
        }
    if isinstance(value, bytes):
        return {"hex": value.hex(), "kind": "bytes"}
    if isinstance(value, complex):
        return {
            "imaginary": _value_shape(value.imag, active),
            "kind": "complex",
            "real": _value_shape(value.real, active),
        }
    if value is Ellipsis:
        return {"kind": "ellipsis"}
    if value is NotImplemented:
        return {"kind": "not-implemented"}
    if isinstance(value, PurePath):
        return {"kind": "path", "value": _stable_path(value)}
    if isinstance(value, range):
        return {
            "kind": "range",
            "start": value.start,
            "step": value.step,
            "stop": value.stop,
        }
    if inspect.isclass(value) or inspect.isroutine(value):
        return {"identity": _identity(value), "kind": "object-reference"}

    if active is None:
        active = set()
    object_id = id(value)
    if object_id in active:
        raise TypeError(
            f"cyclic public ABI value is unsupported: {_type_identity(type(value))}"
        )
    active.add(object_id)
    try:
        if isinstance(value, (Mapping, MappingProxyType)):
            entries = [
                {
                    "key": _value_shape(key, active),
                    "value": _value_shape(item, active),
                }
                for key, item in value.items()
            ]
            entries.sort(key=lambda item: _canonical_sort_key(item["key"]))
            return {
                "entries": entries,
                "kind": "mapping",
                "type": _type_identity(type(value)),
            }
        if isinstance(value, tuple):
            return {
                "items": [_value_shape(item, active) for item in value],
                "kind": "tuple",
            }
        if isinstance(value, list):
            return {
                "items": [_value_shape(item, active) for item in value],
                "kind": "list",
            }
        if isinstance(value, (Set, set, frozenset)):
            items = [_value_shape(item, active) for item in value]
            items.sort(key=_canonical_sort_key)
            return {
                "items": items,
                "kind": "frozenset" if isinstance(value, frozenset) else "set",
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return {
                "items": [_value_shape(item, active) for item in value],
                "kind": "sequence",
                "type": _type_identity(type(value)),
            }
        raise TypeError(
            f"unsupported public ABI value type: {_type_identity(type(value))}"
        )
    finally:
        active.remove(object_id)


def _canonical_sort_key(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _stable_path(path: PurePath) -> str:
    parts = path.parts
    if "pheroos" in parts:
        return "/".join(parts[parts.index("pheroos") :])
    return path.name


__all__: list[str] = []
