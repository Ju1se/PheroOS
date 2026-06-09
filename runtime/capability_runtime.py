from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable

from runtime.capability_registry import CapabilityManifest


DESCRIPTOR_ENTRYPOINTS = {
    "workflow",
    "data_contract",
    "evidence_adapter",
    "output_contract",
    "runtime_support",
    "ui_schema",
    "runtime_nodes",
    "data_provider",
}


class CapabilityEntrypointError(ValueError):
    pass


def load_capability_runtime_descriptors(manifests: list[CapabilityManifest]) -> dict[str, Any]:
    descriptors: dict[str, Any] = {}
    diagnostics: list[dict[str, Any]] = []
    for manifest in manifests:
        try:
            descriptors[manifest.id] = load_capability_descriptor(manifest)
        except CapabilityEntrypointError as exc:
            diagnostics.append({"capability_id": manifest.id, "status": "invalid", "error": str(exc)})
    return {"capabilities": descriptors, "diagnostics": diagnostics}


def load_capability_descriptor(manifest: CapabilityManifest) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    diagnostics: list[dict[str, Any]] = []
    for name, entrypoint in sorted((manifest.entrypoints or {}).items()):
        if name not in DESCRIPTOR_ENTRYPOINTS:
            diagnostics.append({"entrypoint": name, "status": "ignored", "reason": "unknown descriptor entrypoint"})
            continue
        try:
            loaded[name] = load_entrypoint(manifest, name, str(entrypoint))
        except CapabilityEntrypointError as exc:
            diagnostics.append({"entrypoint": name, "status": "invalid", "error": str(exc)})
    enrich_workflow_entrypoint(loaded)
    return {
        "id": manifest.id,
        "name": manifest.name,
        "version": manifest.version,
        "entrypoints": loaded,
        "diagnostics": diagnostics,
    }


def enrich_workflow_entrypoint(entrypoints: dict[str, Any]) -> None:
    workflow = entrypoints.get("workflow")
    if not isinstance(workflow, dict):
        return
    for key in ("data_contract", "evidence_adapter", "output_contract", "runtime_support"):
        descriptor = entrypoints.get(key)
        if isinstance(descriptor, dict) and key not in workflow:
            workflow[key] = descriptor


def load_entrypoint(manifest: CapabilityManifest, name: str, entrypoint: str) -> Any:
    if name == "ui_schema":
        return load_json_entrypoint(manifest, entrypoint)
    if name == "runtime_support" and ":" not in entrypoint:
        return load_python_module_descriptor(manifest, name, entrypoint)
    if ":" not in entrypoint:
        raise CapabilityEntrypointError(f"{manifest.id}.{name} must use path.py:function syntax")
    path_text, function_name = entrypoint.split(":", 1)
    module_path = safe_entrypoint_path(manifest, path_text)
    if not module_path.exists():
        raise CapabilityEntrypointError(f"{manifest.id}.{name} path does not exist: {module_path}")
    function = load_function(module_path, function_name)
    descriptor = function()
    if not isinstance(descriptor, dict):
        raise CapabilityEntrypointError(f"{manifest.id}.{name} returned {type(descriptor).__name__}, expected dict")
    descriptor.setdefault("capability_id", manifest.id)
    descriptor.setdefault("entrypoint", name)
    return descriptor


def load_json_entrypoint(manifest: CapabilityManifest, entrypoint: str) -> Any:
    path = safe_entrypoint_path(manifest, entrypoint)
    if not path.exists():
        raise CapabilityEntrypointError(f"{manifest.id}.ui_schema path does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CapabilityEntrypointError(f"{manifest.id}.ui_schema invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CapabilityEntrypointError(f"{manifest.id}.ui_schema must be a JSON object")
    return payload


def load_python_module_descriptor(manifest: CapabilityManifest, name: str, entrypoint: str) -> dict[str, Any]:
    path = safe_entrypoint_path(manifest, entrypoint)
    if not path.exists():
        raise CapabilityEntrypointError(f"{manifest.id}.{name} path does not exist: {path}")
    if path.suffix != ".py":
        raise CapabilityEntrypointError(f"{manifest.id}.{name} must reference a Python module")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise CapabilityEntrypointError(f"{manifest.id}.{name} invalid Python: {exc}") from exc
    public_functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]
    relative_path = path.relative_to(manifest.path.parent.resolve())
    return {
        "kind": "python_module",
        "path": str(relative_path),
        "public_functions": public_functions[:64],
    }


def safe_entrypoint_path(manifest: CapabilityManifest, entrypoint_path: str) -> Path:
    root = manifest.path.parent.resolve()
    path = Path(entrypoint_path)
    if not path.is_absolute():
        cwd_relative = Path.cwd() / path
        path = cwd_relative if cwd_relative.exists() else root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CapabilityEntrypointError(
            f"{manifest.id} entrypoint must stay inside capability directory: {entrypoint_path}"
        ) from exc
    return resolved


def load_function(module_path: Path, function_name: str) -> Callable[[], Any]:
    if not function_name.isidentifier():
        raise CapabilityEntrypointError(f"invalid function name: {function_name}")
    module_name = f"_capability_entrypoint_{module_path.stem}_{abs(hash(str(module_path))) % 1_000_000}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise CapabilityEntrypointError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, function_name, None)
    if not callable(function):
        raise CapabilityEntrypointError(f"missing callable {function_name} in {module_path}")
    return function
