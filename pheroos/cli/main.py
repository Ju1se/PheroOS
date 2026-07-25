from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import asdict
from importlib import resources
from pathlib import Path
from typing import Any, Callable

from pheroos._version import __version__
from pheroos.conformance import (
    COMMIT_TCK_VERSION,
    CONFORMANCE_REPORT_VERSION,
    profile_for_manifest,
    run_commit_tck,
    run_conformance,
    run_source_conformance,
    validate_manifest,
)
from pheroos.conformance.commit_tck_v2 import (
    run_commit_tck_v2,
    run_commit_tck_v2_jsonl,
)
from pheroos.conformance.commit_tck_v2_protocol import (
    COMMIT_TCK_JSONL_PROTOCOL_VERSION,
    COMMIT_TCK_V2_VERSION,
)
from pheroos.conformance.public_api_inventory import (
    PUBLIC_API_INVENTORY_VERSION,
    build_public_api_inventory,
    public_api_inventory_differences,
)
from pheroos.conformance.schema_catalog import (
    schema_artifact_bytes_for_surface,
    schema_for_surface,
    schema_metadata_for_surface,
    schema_surface_names,
    validate_schema_wire,
)
from pheroos.conformance.stable_api_candidate import (
    build_stable_api_candidate,
    promotion_candidate_differences,
    promotion_candidate_public_inventory_differences,
    stable_api_breaking_differences,
    stable_public_inventory_breaking_differences,
)
from pheroos.conformance.stable_api_roots import STABLE_API_CANDIDATE_VERSION
from pheroos.drivers._versions import (
    DRIVER_DESCRIPTOR_VERSION_V2,
    DRIVER_INVOCATION_RECEIPT_VERSION,
    DRIVER_INVOCATION_VERSION,
)
from pheroos.governance.authority_domain import AUTHORITY_LEDGER_VERSION
from pheroos.kernel._versions import KERNEL_PLAN_VERSION_V2
from pheroos.protocol.authority_schema_v2 import (
    CAPABILITY_SCHEMA_V3,
    PROTOCOL_SCHEMA_V3,
)
from pheroos.protocol.loader import (
    parse_finite_json_float,
    reject_duplicate_json_object_keys,
    reject_non_finite_json_constant,
)
from pheroos.protocol.models import (
    SUPPORTED_PROTOCOL_VERSIONS,
    CapabilityManifest,
)
from pheroos.protocol.schema import (
    CAPABILITY_SCHEMA_V1,
    CAPABILITY_SCHEMA_V2,
    PROTOCOL_SCHEMA_V1,
    PROTOCOL_SCHEMA_V2,
)
from pheroos.protocol.schema_document import read_capability_manifest
from pheroos.protocol.validation import validate_capability_manifest
from pheroos.trace import SCOPED_TRACE_EVENT_VERSION

CLI_OUTPUT_VERSION = "pheroos-cli-output-v1"
WIRE_VALIDATION_REPORT_VERSION = "pheroos-wire-validation-report-v1"
ABI_COMMAND_REPORT_VERSION = "pheroos-abi-command-report-v1"

SCHEMA_SURFACES = schema_surface_names()
WIRE_SURFACES = SCHEMA_SURFACES


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args, parser)
    except (OSError, TypeError, ValueError) as exc:
        return emit_report(
            {
                "output_version": CLI_OUTPUT_VERSION,
                "ok": False,
                "error_code": "cli_input_invalid",
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
            failure_code=2,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pheroos")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version")

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("path")

    conformance_parser = sub.add_parser("conformance")
    conformance_parser.add_argument("path")

    source_conformance_parser = sub.add_parser("source-conformance")
    source_conformance_parser.add_argument("core_root", nargs="?")

    profile_parser = sub.add_parser("profile")
    profile_sub = profile_parser.add_subparsers(
        dest="profile_command",
        required=True,
    )
    profile_show = profile_sub.add_parser("show")
    profile_show.add_argument("path")

    schema_parser = sub.add_parser("schema")
    schema_sub = schema_parser.add_subparsers(dest="schema_command", required=True)
    schema_sub.add_parser("list")
    for command in ("show", "export"):
        schema_surface = schema_sub.add_parser(command)
        schema_surface.add_argument("surface", choices=SCHEMA_SURFACES)

    wire_parser = sub.add_parser("wire")
    wire_sub = wire_parser.add_subparsers(dest="wire_command", required=True)
    wire_validate = wire_sub.add_parser("validate")
    wire_validate.add_argument("surface", choices=WIRE_SURFACES)
    wire_validate.add_argument("path")

    tck_parser = sub.add_parser("tck")
    tck_sub = tck_parser.add_subparsers(dest="tck_command", required=True)
    tck_run = tck_sub.add_parser("run")
    tck_run.add_argument("--version", choices=("v1", "v2"), default="v2")
    tck_run.add_argument(
        "--adapter",
        help="quoted JSONL adapter command; supported by TCK v2",
    )
    tck_run.add_argument("--timeout", type=float, default=15.0)

    abi_parser = sub.add_parser("abi")
    abi_sub = abi_parser.add_subparsers(dest="abi_command", required=True)
    abi_show = abi_sub.add_parser("show")
    abi_show.add_argument("--package")
    abi_show.add_argument(
        "--stable-only",
        action="store_true",
        help="show only the reviewed Draft promotion-candidate closure",
    )
    abi_diff = abi_sub.add_parser("diff")
    abi_diff.add_argument(
        "path",
        nargs="?",
        help="inventory JSON to compare; defaults to the running Python ABI",
    )
    abi_diff.add_argument(
        "--stable-only",
        action="store_true",
        help="compare only the reviewed Draft promotion-candidate closure",
    )
    return parser


def _dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    direct_payloads: dict[str, Callable[[], dict[str, Any]]] = {
        "version": version_payload,
        "validate": lambda: validate_manifest(args.path).to_dict(),
        "conformance": lambda: run_conformance(args.path).to_dict(),
        "source-conformance": lambda: run_source_conformance(args.core_root).to_dict(),
    }
    direct_payload = direct_payloads.get(args.command)
    if direct_payload is not None:
        return emit_report(direct_payload())
    if args.command == "profile" and args.profile_command == "show":
        return emit_report(profile_payload(args.path))
    if args.command == "schema":
        return _dispatch_schema(args, parser)
    if args.command == "wire" and args.wire_command == "validate":
        return emit_report(wire_validation_payload(args.surface, args.path))
    if args.command == "tck" and args.tck_command == "run":
        return emit_report(tck_payload(args.version, args.adapter, args.timeout))
    if args.command == "abi":
        return _dispatch_abi(args, parser)
    parser.error("unknown command")
    return 2


def _dispatch_schema(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int:
    if args.schema_command == "list":
        return emit_report(schema_list_payload())
    if args.schema_command in {"show", "export"}:
        return emit_schema_artifact(args.surface)
    parser.error("unknown schema command")
    return 2


def _dispatch_abi(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int:
    if args.abi_command == "show":
        return emit_report(abi_show_payload(args.package, stable_only=args.stable_only))
    if args.abi_command == "diff":
        return emit_report(abi_diff_payload(args.path, stable_only=args.stable_only))
    parser.error("unknown ABI command")
    return 2


def emit_report(payload: dict[str, Any], *, failure_code: int = 1) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok", True) is not False else failure_code


def emit_schema_artifact(surface: str) -> int:
    """Write canonical Schema bytes, including byte-frozen legacy ordering."""

    print(schema_artifact_bytes_for_surface(surface).decode("utf-8"), end="")
    return 0


def version_payload() -> dict[str, Any]:
    return {
        "output_version": CLI_OUTPUT_VERSION,
        "ok": True,
        "package_version": __version__,
        "protocol_versions": sorted(SUPPORTED_PROTOCOL_VERSIONS),
        "capability_schema_versions": [
            CAPABILITY_SCHEMA_V1,
            CAPABILITY_SCHEMA_V2,
            CAPABILITY_SCHEMA_V3,
        ],
        "protocol_schema_versions": [
            PROTOCOL_SCHEMA_V1,
            PROTOCOL_SCHEMA_V2,
            PROTOCOL_SCHEMA_V3,
        ],
        "authority_ledger_version": AUTHORITY_LEDGER_VERSION,
        "driver_descriptor_version": DRIVER_DESCRIPTOR_VERSION_V2,
        "driver_invocation_version": DRIVER_INVOCATION_VERSION,
        "driver_receipt_version": DRIVER_INVOCATION_RECEIPT_VERSION,
        "kernel_plan_version": KERNEL_PLAN_VERSION_V2,
        "scoped_trace_version": SCOPED_TRACE_EVENT_VERSION,
        "conformance_report_version": CONFORMANCE_REPORT_VERSION,
        "commit_tck_versions": [COMMIT_TCK_VERSION, COMMIT_TCK_V2_VERSION],
        "commit_tck_adapter_protocol": COMMIT_TCK_JSONL_PROTOCOL_VERSION,
    }


def profile_payload(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path)
    manifest = read_capability_manifest(
        _object(payload, "capability manifest"),
        schema_version=CAPABILITY_SCHEMA_V2,
    )
    if not isinstance(manifest, CapabilityManifest):
        raise ValueError("profile requires a legacy capability manifest")
    diagnostics = validate_capability_manifest(manifest)
    if diagnostics:
        return {
            "output_version": CLI_OUTPUT_VERSION,
            "ok": False,
            "subject": str(path),
            "diagnostics": [item.to_dict() for item in diagnostics],
        }
    profile = profile_for_manifest(manifest)
    return {
        "output_version": CLI_OUTPUT_VERSION,
        "ok": True,
        "subject": str(path),
        "protocol_version": manifest.protocol.protocol_version,
        "profile": {
            "name": profile.name,
            "version": profile.version,
            "required_checks": list(profile.required_checks),
        },
    }


def schema_list_payload() -> dict[str, Any]:
    return {
        "output_version": CLI_OUTPUT_VERSION,
        "ok": True,
        "schemas": [schema_metadata(surface) for surface in SCHEMA_SURFACES],
    }


def schema_metadata(surface: str) -> dict[str, object]:
    return schema_metadata_for_surface(surface)


def schema_for(surface: str) -> dict[str, Any]:
    return schema_for_surface(surface)


def wire_validation_payload(surface: str, path: str | Path) -> dict[str, Any]:
    diagnostics: list[dict[str, str]] = []
    try:
        payload = _load_json(path)
        _validate_wire_payload(surface, payload, path)
    except (OSError, TypeError, ValueError) as exc:
        diagnostics.append(
            {
                "code": str(getattr(exc, "code", "wire_validation_failed")),
                "message": str(exc),
                "path": str(path),
                "field_path": str(getattr(exc, "path", "$")),
            }
        )
    return {
        "report_version": WIRE_VALIDATION_REPORT_VERSION,
        "ok": not diagnostics,
        "surface": surface,
        "subject": str(path),
        "diagnostics": diagnostics,
    }


def _validate_wire_payload(surface: str, payload: Any, path: str | Path) -> None:
    validate_schema_wire(surface, payload, path)


def tck_payload(version: str, adapter: str | None, timeout: float) -> dict[str, Any]:
    if version == "v1":
        if adapter:
            raise ValueError("Commit TCK v1 does not expose the JSONL adapter ABI")
        v1_report = run_commit_tck()
        return {
            "output_version": CLI_OUTPUT_VERSION,
            "ok": v1_report.ok,
            "tck_version": v1_report.tck_version,
            "results": [asdict(item) for item in v1_report.results],
        }
    if version != "v2":
        raise ValueError("Commit TCK version is unsupported")
    v2_report = (
        run_commit_tck_v2_jsonl(
            shlex.split(adapter),
            timeout=timeout,
        )
        if adapter
        else run_commit_tck_v2()
    )
    return {
        "output_version": CLI_OUTPUT_VERSION,
        "ok": v2_report.ok,
        "tck_version": v2_report.tck_version,
        "implementation_id": v2_report.implementation_id,
        "protocol_error": v2_report.protocol_error,
        "results": [asdict(item) for item in v2_report.results],
    }


def abi_show_payload(
    package: str | None = None,
    *,
    stable_only: bool = False,
) -> dict[str, Any]:
    inventory = (
        _load_packaged_stable_api_candidate()
        if stable_only
        else _load_packaged_abi_inventory()
    )
    if package is not None:
        packages = inventory.get("packages", {})
        if package not in packages:
            raise ValueError(f"unknown ABI package: {package}")
        inventory = {
            "artifact_version": inventory["artifact_version"],
            "package": package,
            "surface": packages[package],
        }
    return {
        "report_version": ABI_COMMAND_REPORT_VERSION,
        "ok": True,
        "stable_only": stable_only,
        "inventory": inventory,
    }


def abi_diff_payload(
    path: str | Path | None = None,
    *,
    stable_only: bool = False,
) -> dict[str, Any]:
    if stable_only:
        return _stable_abi_diff_payload(path)
    expected = _load_packaged_abi_inventory()
    observed = _load_json(path) if path is not None else build_public_api_inventory()
    differences = public_api_inventory_differences(expected, observed)
    return {
        "report_version": ABI_COMMAND_REPORT_VERSION,
        "ok": not differences,
        "stable_only": False,
        "expected_version": expected.get("artifact_version", ""),
        "observed_version": (
            observed.get("artifact_version", "") if isinstance(observed, dict) else ""
        ),
        "differences": differences,
    }


def _stable_abi_diff_payload(path: str | Path | None) -> dict[str, Any]:
    expected = _load_packaged_stable_api_candidate()
    observed = _load_json(path) if path is not None else build_stable_api_candidate()
    if not isinstance(observed, dict):
        raise TypeError("Stable ABI observation must be a JSON object")
    observed_version = observed.get("artifact_version")
    if observed_version == STABLE_API_CANDIDATE_VERSION:
        differences = promotion_candidate_differences(expected, observed)
        breaking = stable_api_breaking_differences(expected, observed)
    elif observed_version == PUBLIC_API_INVENTORY_VERSION:
        expected_inventory = _load_packaged_abi_inventory()
        differences = promotion_candidate_public_inventory_differences(
            expected,
            expected_inventory,
            observed,
        )
        breaking = stable_public_inventory_breaking_differences(
            expected,
            expected_inventory,
            observed,
            observed_compatibility_major=_compatibility_major(expected),
        )
    else:
        raise ValueError(
            "--stable-only ABI diff requires a Stable candidate or public ABI "
            "inventory artifact"
        )
    lifecycle = expected.get("lifecycle")
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    return {
        "report_version": ABI_COMMAND_REPORT_VERSION,
        "ok": not differences,
        "stable_only": True,
        "candidate_status": lifecycle.get("status", ""),
        "formal_stable": lifecycle.get("formal_stable") is True,
        "stable_breaking": bool(breaking),
        "expected_version": expected.get("artifact_version", ""),
        "observed_version": observed_version,
        "differences": differences,
        "breaking_differences": breaking,
    }


def _compatibility_major(candidate: dict[str, Any]) -> int:
    value = candidate.get("compatibility_major")
    if type(value) is not int:
        raise ValueError("Stable candidate compatibility_major must be an integer")
    return value


def _load_packaged_abi_inventory() -> dict[str, Any]:
    resource = resources.files("pheroos.conformance").joinpath(
        "abi",
        "public-python-api-v1.json",
    )
    loaded = json.loads(resource.read_text(encoding="utf-8"))
    return _object(loaded, "public ABI inventory")


def _load_packaged_stable_api_candidate() -> dict[str, Any]:
    resource = resources.files("pheroos.conformance").joinpath(
        "abi",
        "stable-python-api-v1.json",
    )
    loaded = json.loads(resource.read_text(encoding="utf-8"))
    return _object(loaded, "Stable API promotion candidate")


def _load_json(path: str | Path | None) -> Any:
    if path is None:
        raise ValueError("JSON path is required")
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=reject_non_finite_json_constant,
        parse_float=parse_finite_json_float,
        object_pairs_hook=reject_duplicate_json_object_keys,
    )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
