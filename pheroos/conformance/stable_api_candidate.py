"""Build and audit the Draft Stable Python API promotion candidate.

The checked artifact is a filtered, transitively type-closed view of the
existing six public facades.  It does not publish new facade bindings and does
not change lifecycle state.  Formal Stable compatibility checks become active
only when a later, separately approved artifact has ``stability == "stable"``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import fields, is_dataclass
from importlib import import_module
import inspect
import json
from pathlib import Path
from types import UnionType
from typing import Any, ForwardRef, TypeVar, get_args, get_origin, get_type_hints

from pheroos.conformance.public_api_inventory import (
    PUBLIC_PACKAGES,
    build_public_api_inventory,
)
from pheroos.conformance.public_api_lifecycle import build_public_api_lifecycle
from pheroos.conformance._stable_api_validation import (
    artifact_root as _artifact_root,
    candidate_summary as _summary,
    promotion_candidate_differences,
    promotion_candidate_public_inventory_differences,
    stable_api_breaking_differences,
    stable_api_candidate_problems,
    stable_public_inventory_breaking_differences,
)
from pheroos.conformance.stable_api_roots import (
    STABLE_API_CANDIDATE_ROOTS,
    STABLE_API_CANDIDATE_STABILITY,
    STABLE_API_CANDIDATE_STATUS,
    STABLE_API_CANDIDATE_VERSION,
    STABLE_API_CLOSURE_BUDGET,
    STABLE_API_COMPATIBILITY_MAJOR,
    STABLE_API_CONSTANT_DEPENDENCIES,
    STABLE_API_CURRENT_ROOT_TARGET,
    STABLE_API_EXCEPTION_DEPENDENCIES,
    STABLE_API_FORBIDDEN_BINDINGS,
    STABLE_API_GOVERNANCE_CLOSURE_BUDGET,
    STABLE_API_GOVERNANCE_ROOT_BUDGET,
    STABLE_API_ROOT_BUDGET,
)


STABLE_API_CANDIDATE_PATH = Path("pheroos/conformance/abi/stable-python-api-v1.json")

_Binding = tuple[str, str]


def build_stable_api_candidate(
    source_root: str | Path | None = None,
    *,
    roots: Mapping[str, Sequence[str]] = STABLE_API_CANDIDATE_ROOTS,
) -> dict[str, Any]:
    """Return the current Draft promotion candidate and its type closure."""

    inventory = build_public_api_inventory()
    lifecycle = build_public_api_lifecycle(source_root)
    shapes = _shape_index(inventory)
    lifecycles = _lifecycle_index(lifecycle)
    objects = _object_index(shapes)
    canonical = _canonical_bindings(objects, shapes, lifecycles)
    root_bindings = _root_bindings(roots, shapes)
    exception_dependencies = _declared_dependencies(
        STABLE_API_EXCEPTION_DEPENDENCIES,
        shapes,
        dependency_kind="exception",
    )
    constant_dependencies = _declared_dependencies(
        STABLE_API_CONSTANT_DEPENDENCIES,
        shapes,
        dependency_kind="constant",
    )
    closure, references, exception_references, bases, missing = _type_closure(
        root_bindings,
        objects,
        canonical,
        exception_dependencies,
    )
    surface_diagnostics = _surface_diagnostics(closure, objects, shapes)
    entries = [
        _candidate_entry(
            binding,
            shapes[binding],
            lifecycles[binding],
            canonical.get(id(objects[binding]), binding),
            binding in root_bindings,
            references.get(binding, set()),
            exception_references.get(binding, set()),
            constant_dependencies.get(binding, set()),
            bases.get(binding, set()),
        )
        for binding in sorted(closure)
    ]
    packages = _package_entries(entries, root_bindings)
    constants = _constant_dependency_entries(
        closure,
        constant_dependencies,
        shapes,
        lifecycles,
    )
    artifact: dict[str, Any] = {
        "artifact_version": STABLE_API_CANDIDATE_VERSION,
        "budgets": {
            "closure": STABLE_API_CLOSURE_BUDGET,
            "governance_closure": STABLE_API_GOVERNANCE_CLOSURE_BUDGET,
            "governance_roots": STABLE_API_GOVERNANCE_ROOT_BUDGET,
            "roots": STABLE_API_ROOT_BUDGET,
        },
        "closure_policy": {
            "canonical_owner_required": True,
            "compatibility_bindings_allowed": False,
            "declared_public_exceptions": True,
            "dataclass_fields": True,
            "deprecated_bindings_allowed": False,
            "direct_class_methods_and_properties": True,
            "nonportable_opaque_authority_allowed": False,
            "public_constant_value_dependencies": True,
            "public_base_types": True,
            "signature_parameters_and_returns": True,
        },
        "compatibility_major": STABLE_API_COMPATIBILITY_MAJOR,
        "constant_dependencies": constants,
        "lifecycle": {
            "formal_stable": False,
            "stability": STABLE_API_CANDIDATE_STABILITY,
            "status": STABLE_API_CANDIDATE_STATUS,
        },
        "packages": packages,
        "review_targets": {"roots": STABLE_API_CURRENT_ROOT_TARGET},
        "resolution_diagnostics": sorted(missing),
        "surface_diagnostics": sorted(surface_diagnostics),
        "summary": _summary(packages, {item["binding"]: item for item in constants}),
    }
    artifact["artifact_root"] = _artifact_root(artifact)
    return artifact


def render_stable_api_candidate(candidate: Mapping[str, Any]) -> str:
    """Render a deterministic candidate artifact."""

    return (
        json.dumps(
            candidate,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def load_stable_api_candidate(root: str | Path) -> dict[str, Any]:
    """Load the checked promotion candidate rooted at a source tree."""

    value = json.loads(
        (Path(root) / STABLE_API_CANDIDATE_PATH).read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise ValueError("Stable API candidate artifact must be a JSON object")
    return value


def _shape_index(inventory: Mapping[str, Any]) -> dict[_Binding, dict[str, Any]]:
    index: dict[_Binding, dict[str, Any]] = {}
    for package_name in PUBLIC_PACKAGES:
        package = inventory["packages"][package_name]
        for shape in package["exports"]:
            index[(package_name, shape["name"])] = shape
    return index


def _lifecycle_index(lifecycle: Mapping[str, Any]) -> dict[_Binding, dict[str, Any]]:
    index: dict[_Binding, dict[str, Any]] = {}
    for package_name in PUBLIC_PACKAGES:
        package = lifecycle["packages"][package_name]
        for entry in package["exports"]:
            index[(package_name, entry["name"])] = entry
    return index


def _object_index(shapes: Mapping[_Binding, Any]) -> dict[_Binding, Any]:
    modules = {name: import_module(name) for name in PUBLIC_PACKAGES}
    return {binding: getattr(modules[binding[0]], binding[1]) for binding in shapes}


def _canonical_bindings(
    objects: Mapping[_Binding, Any],
    shapes: Mapping[_Binding, Mapping[str, Any]],
    lifecycles: Mapping[_Binding, Mapping[str, Any]],
) -> dict[int, _Binding]:
    candidates: dict[int, list[_Binding]] = {}
    for binding, value in objects.items():
        if inspect.isclass(value) or inspect.isroutine(value):
            candidates.setdefault(id(value), []).append(binding)
    return {
        object_id: min(
            bindings,
            key=lambda item: _canonical_rank(
                item,
                objects[item],
                shapes[item],
                lifecycles[item],
            ),
        )
        for object_id, bindings in candidates.items()
    }


def _canonical_rank(
    binding: _Binding,
    value: Any,
    shape: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
) -> tuple[int, int, int, str]:
    module = str(getattr(value, "__module__", ""))
    public_name = str(getattr(value, "__name__", ""))
    excluded = (
        lifecycle.get("stability") == "deprecated"
        or lifecycle.get("group") == "compatibility"
    )
    package_mismatch = not (module == binding[0] or module.startswith(f"{binding[0]}."))
    name_mismatch = binding[1] not in {public_name, shape.get("attribute")}
    return (
        int(excluded),
        int(package_mismatch),
        int(name_mismatch),
        _qualified(binding),
    )


def _root_bindings(
    roots: Mapping[str, Sequence[str]],
    shapes: Mapping[_Binding, Any],
) -> set[_Binding]:
    selected = {
        (package_name, name) for package_name, names in roots.items() for name in names
    }
    unknown = sorted(selected - set(shapes))
    if unknown:
        names = ", ".join(_qualified(item) for item in unknown)
        raise ValueError(f"unknown Stable API candidate root(s): {names}")
    return selected


def _declared_dependencies(
    decisions: Mapping[str, Sequence[str]],
    shapes: Mapping[_Binding, Any],
    *,
    dependency_kind: str,
) -> dict[_Binding, set[_Binding]]:
    dependencies: dict[_Binding, set[_Binding]] = {}
    unknown: set[str] = set()
    for source_name, target_names in decisions.items():
        source = _split_qualified(source_name)
        if source not in shapes:
            unknown.add(source_name)
            continue
        for target_name in target_names:
            target = _split_qualified(target_name)
            if target not in shapes:
                unknown.add(target_name)
                continue
            dependencies.setdefault(source, set()).add(target)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unknown Stable API {dependency_kind} dependency: {names}")
    return dependencies


def _split_qualified(value: str) -> _Binding:
    package_name, name = value.rsplit(".", 1)
    return package_name, name


def _type_closure(
    roots: set[_Binding],
    objects: Mapping[_Binding, Any],
    canonical: Mapping[int, _Binding],
    exception_dependencies: Mapping[_Binding, set[_Binding]],
) -> tuple[
    set[_Binding],
    dict[_Binding, set[_Binding]],
    dict[_Binding, set[_Binding]],
    dict[_Binding, set[_Binding]],
    set[str],
]:
    selected: set[_Binding] = set()
    references: dict[_Binding, set[_Binding]] = {}
    exception_references: dict[_Binding, set[_Binding]] = {}
    bases: dict[_Binding, set[_Binding]] = {}
    missing: set[str] = set()
    queue = deque(sorted(roots))
    while queue:
        binding = queue.popleft()
        if binding in selected:
            continue
        selected.add(binding)
        refs, public_bases, unresolved = _binding_references(
            binding,
            objects[binding],
            canonical,
        )
        exceptions = set(exception_dependencies.get(binding, set()))
        refs.update(exceptions)
        references[binding] = refs
        exception_references[binding] = exceptions
        bases[binding] = public_bases
        missing.update(unresolved)
        queue.extend(sorted(refs - selected))
    return selected, references, exception_references, bases, missing


def _binding_references(
    binding: _Binding,
    value: Any,
    canonical: Mapping[int, _Binding],
) -> tuple[set[_Binding], set[_Binding], set[str]]:
    annotations: list[Any] = []
    base_bindings: set[_Binding] = set()
    if inspect.isclass(value):
        for base in value.__bases__:
            public = canonical.get(id(base))
            if public is not None:
                base_bindings.add(public)
        annotations.extend(_constructor_annotations(value))
        if is_dataclass(value):
            hints = _safe_hints(value)
            annotations.extend(
                hints.get(item.name, item.type) for item in fields(value)
            )
        annotations.extend(_class_member_annotations(value))
    elif inspect.isroutine(value):
        annotations.extend(_safe_hints(value).values())
    references = set(base_bindings)
    missing: set[str] = set()
    for annotation in annotations:
        _collect_annotation_references(
            annotation,
            binding,
            canonical,
            references,
            missing,
        )
    references.discard(binding)
    return references, base_bindings, missing


def _constructor_annotations(value: type[Any]) -> list[Any]:
    annotations: list[Any] = []
    for name in ("__new__", "__init__"):
        constructor = value.__dict__.get(name)
        if isinstance(constructor, (staticmethod, classmethod)):
            constructor = constructor.__func__
        if callable(constructor):
            annotations.extend(_safe_hints(constructor).values())
    return annotations


def _class_member_annotations(value: type[Any]) -> list[Any]:
    annotations: list[Any] = []
    for name, descriptor in value.__dict__.items():
        if name.startswith("_"):
            continue
        callables: tuple[Any, ...]
        if isinstance(descriptor, (staticmethod, classmethod)):
            callables = (descriptor.__func__,)
        elif isinstance(descriptor, property):
            callables = tuple(
                item for item in (descriptor.fget, descriptor.fset) if item is not None
            )
        elif inspect.isfunction(descriptor):
            callables = (descriptor,)
        else:
            callables = ()
        for function in callables:
            annotations.extend(_safe_hints(function).values())
    return annotations


def _safe_hints(value: Any) -> dict[str, Any]:
    try:
        return get_type_hints(value, include_extras=True)
    except (NameError, TypeError):
        annotations = getattr(value, "__annotations__", {})
        return dict(annotations) if isinstance(annotations, dict) else {}


def _collect_annotation_references(
    annotation: Any,
    source: _Binding,
    canonical: Mapping[int, _Binding],
    references: set[_Binding],
    missing: set[str],
) -> None:
    if annotation is None or annotation is inspect.Signature.empty:
        return
    public = canonical.get(id(annotation))
    if public is not None:
        references.add(public)
        return
    if isinstance(annotation, TypeVar):
        for item in (*annotation.__constraints__, annotation.__bound__):
            _collect_annotation_references(item, source, canonical, references, missing)
        return
    if isinstance(annotation, ForwardRef):
        missing.add(f"{_qualified(source)}:{annotation.__forward_arg__}")
        return
    origin = get_origin(annotation)
    if origin is not None or isinstance(annotation, UnionType):
        for item in get_args(annotation):
            _collect_annotation_references(item, source, canonical, references, missing)
        return
    module = getattr(annotation, "__module__", "")
    if isinstance(module, str) and module.startswith("pheroos"):
        name = getattr(annotation, "__qualname__", repr(annotation))
        # Collective policy keeps its private pheromone profile type in the
        # runtime annotation, but that type is intentionally no longer part of
        # any public facade.  A Draft Stable candidate must not manufacture a
        # public closure entry for a private implementation detail.
        if module == "pheroos.protocol.models" and name == "PheromoneKindProfile":
            return
        missing.add(f"{_qualified(source)}:{module}:{name}")


def _candidate_entry(
    binding: _Binding,
    shape: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    canonical_binding: _Binding,
    is_root: bool,
    references: set[_Binding],
    exception_references: set[_Binding],
    constant_dependencies: set[_Binding],
    bases: set[_Binding],
) -> dict[str, Any]:
    return {
        "binding": _qualified(binding),
        "canonical_binding": _qualified(canonical_binding),
        "constant_dependencies": [
            _qualified(item) for item in sorted(constant_dependencies)
        ],
        "exception_references": [
            _qualified(item) for item in sorted(exception_references)
        ],
        "lifecycle_group": lifecycle["group"],
        "lifecycle_stability": lifecycle["stability"],
        "membership": "root" if is_root else "dependency",
        "public_bases": [_qualified(item) for item in sorted(bases)],
        "references": [_qualified(item) for item in sorted(references)],
        "shape": deepcopy(shape),
    }


def _constant_dependency_entries(
    closure: set[_Binding],
    dependencies: Mapping[_Binding, set[_Binding]],
    shapes: Mapping[_Binding, Mapping[str, Any]],
    lifecycles: Mapping[_Binding, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    selected = {
        target
        for source, targets in dependencies.items()
        if source in closure
        for target in targets
    }
    return [
        {
            "binding": _qualified(binding),
            "lifecycle_group": lifecycles[binding]["group"],
            "lifecycle_stability": lifecycles[binding]["stability"],
            "shape": _constant_public_shape(shapes[binding]),
        }
        for binding in sorted(selected)
    ]


def _constant_public_shape(shape: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the public binding owner and value, never an implementation owner."""

    return {
        "attribute": deepcopy(shape.get("attribute")),
        "binding_owner": deepcopy(shape.get("binding_owner")),
        "constant": deepcopy(shape.get("constant")),
        "kind": deepcopy(shape.get("kind")),
        "name": deepcopy(shape.get("name")),
    }


def _surface_diagnostics(
    closure: set[_Binding],
    objects: Mapping[_Binding, Any],
    shapes: Mapping[_Binding, Mapping[str, Any]],
) -> set[str]:
    diagnostics: set[str] = set()
    for binding in closure:
        qualified = _qualified(binding)
        if qualified in STABLE_API_FORBIDDEN_BINDINGS or _is_nonportable_opaque(
            objects[binding]
        ):
            diagnostics.add(f"nonportable_opaque:{qualified}")
        owner = shapes[binding].get("binding_owner")
        if not _is_public_owner(owner):
            diagnostics.add(f"internal_binding_owner:{qualified}:{owner}")
    return diagnostics


def _is_nonportable_opaque(value: Any) -> bool:
    if not inspect.isclass(value):
        return False
    for name in ("__reduce__", "__reduce_ex__", "__getstate__"):
        method = value.__dict__.get(name)
        if method is None:
            continue
        try:
            source = inspect.getsource(method)
        except (OSError, TypeError):
            continue
        if "not portable" in source:
            return True
    return False


def _is_public_owner(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("pheroos.")
        and not any(item.startswith("_") for item in value.split("."))
    )


def _package_entries(
    entries: Sequence[Mapping[str, Any]],
    roots: set[_Binding],
) -> dict[str, Any]:
    packages: dict[str, Any] = {}
    for package_name in PUBLIC_PACKAGES:
        selected = [
            dict(item)
            for item in entries
            if item["binding"].rsplit(".", 1)[0] == package_name
        ]
        root_names = sorted(name for package, name in roots if package == package_name)
        packages[package_name] = {
            "closure_count": len(selected),
            "exports": selected,
            "root_count": len(root_names),
            "roots": root_names,
        }
    return packages


def _qualified(binding: _Binding) -> str:
    return f"{binding[0]}.{binding[1]}"


__all__ = [
    "STABLE_API_CANDIDATE_PATH",
    "build_stable_api_candidate",
    "load_stable_api_candidate",
    "promotion_candidate_differences",
    "promotion_candidate_public_inventory_differences",
    "render_stable_api_candidate",
    "stable_api_breaking_differences",
    "stable_api_candidate_problems",
    "stable_public_inventory_breaking_differences",
]
