from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
from importlib import resources
import json
from pathlib import Path
import shlex
from typing import Any

from pheroos._version import __version__
from pheroos.conformance import (
    COMMIT_TCK_VERSION,
    CONFORMANCE_REPORT_VERSION,
    ConformanceReport,
    commit_tck_schema,
    conformance_report_schema,
    profile_for_manifest,
    run_commit_tck,
    run_conformance,
    run_source_conformance,
    validate_manifest,
)
from pheroos.conformance.commit_tck import load_commit_tck_vectors
from pheroos.conformance.commit_tck_v2 import (
    commit_tck_v2_schema,
    load_commit_tck_v2_cases,
    run_commit_tck_v2,
    run_commit_tck_v2_jsonl,
)
from pheroos.conformance.commit_tck_v2_protocol import (
    COMMIT_TCK_JSONL_PROTOCOL_VERSION,
    COMMIT_TCK_V2_VERSION,
    CommitTckRequest,
    CommitTckResponse,
    commit_tck_request_v2_schema,
    commit_tck_response_v2_schema,
)
from pheroos.conformance.public_api_inventory import (
    build_public_api_inventory,
    public_api_inventory_differences,
)
from pheroos.drivers._versions import (
    DRIVER_DESCRIPTOR_VERSION_V2,
    DRIVER_INVOCATION_RECEIPT_VERSION,
    DRIVER_INVOCATION_VERSION,
)
from pheroos.drivers.document import (
    driver_descriptor_from_dict,
    driver_descriptor_v1_from_dict,
)
from pheroos.drivers.schema import driver_schema, driver_schema_v2
from pheroos.governance.authority_domain import AUTHORITY_LEDGER_VERSION
from pheroos.governance.schema import commit_schema, validate_commit_wire_record
from pheroos.kernel.plan_document import os_plan_from_dict, os_plan_v1_from_dict
from pheroos.kernel._versions import KERNEL_PLAN_VERSION_V2
from pheroos.kernel.schema import kernel_schema, kernel_schema_v2
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
    capability_schema,
    capability_schema_v2,
    protocol_schema,
    protocol_schema_v2,
)
from pheroos.protocol.schema_document import (
    read_capability_manifest,
    read_protocol_manifest,
)
from pheroos.protocol.validation import validate_capability_manifest
from pheroos.trace import (
    SCOPED_TRACE_EVENT_VERSION,
    ScopedTraceEvent,
    TraceEvent,
    scoped_trace_event_schema,
)
from pheroos.trace.schema import trace_schema


CLI_OUTPUT_VERSION = "pheroos-cli-output-v1"
WIRE_VALIDATION_REPORT_VERSION = "pheroos-wire-validation-report-v1"
ABI_COMMAND_REPORT_VERSION = "pheroos-abi-command-report-v1"

SCHEMA_SURFACES = (
    "capability",
    "capability-v1",
    "capability-v2",
    "protocol",
    "protocol-v1",
    "protocol-v2",
    "kernel",
    "kernel-v1",
    "kernel-v2",
    "driver",
    "driver-v1",
    "driver-v2",
    "trace",
    "commit",
    "conformance-report",
    "scoped-trace",
    "commit-tck-v1",
    "commit-tck-v2",
    "commit-tck-request-v2",
    "commit-tck-response-v2",
)
WIRE_SURFACES = (
    "capability",
    "capability-v1",
    "capability-v2",
    "protocol",
    "protocol-v1",
    "protocol-v2",
    "kernel",
    "kernel-v1",
    "kernel-v2",
    "driver",
    "driver-v1",
    "driver-v2",
    "commit",
    "trace",
    "scoped-trace",
    "conformance-report",
    "commit-tck-v1",
    "commit-tck-v2",
    "commit-tck-request-v2",
    "commit-tck-response-v2",
)


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
    abi_diff = abi_sub.add_parser("diff")
    abi_diff.add_argument(
        "path",
        nargs="?",
        help="inventory JSON to compare; defaults to the running Python ABI",
    )
    return parser


def _dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "version":
        return emit_report(version_payload())
    if args.command == "validate":
        return emit_report(validate_manifest(args.path).to_dict())
    if args.command == "conformance":
        return emit_report(run_conformance(args.path).to_dict())
    if args.command == "source-conformance":
        return emit_report(run_source_conformance(args.core_root).to_dict())
    if args.command == "profile" and args.profile_command == "show":
        return emit_report(profile_payload(args.path))
    if args.command == "schema":
        if args.schema_command == "list":
            return emit_report(schema_list_payload())
        if args.schema_command in {"show", "export"}:
            return emit_report(schema_for(args.surface))
    if args.command == "wire" and args.wire_command == "validate":
        return emit_report(wire_validation_payload(args.surface, args.path))
    if args.command == "tck" and args.tck_command == "run":
        return emit_report(tck_payload(args.version, args.adapter, args.timeout))
    if args.command == "abi":
        if args.abi_command == "show":
            return emit_report(abi_show_payload(args.package))
        if args.abi_command == "diff":
            return emit_report(abi_diff_payload(args.path))
    parser.error("unknown command")
    return 2


def emit_report(payload: dict[str, Any], *, failure_code: int = 1) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok", True) is not False else failure_code


def version_payload() -> dict[str, Any]:
    return {
        "output_version": CLI_OUTPUT_VERSION,
        "ok": True,
        "package_version": __version__,
        "protocol_versions": sorted(SUPPORTED_PROTOCOL_VERSIONS),
        "capability_schema_versions": [
            CAPABILITY_SCHEMA_V1,
            CAPABILITY_SCHEMA_V2,
        ],
        "protocol_schema_versions": [PROTOCOL_SCHEMA_V1, PROTOCOL_SCHEMA_V2],
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
        "schemas": [
            schema_metadata(surface)
            for surface in SCHEMA_SURFACES
        ],
    }


def schema_metadata(surface: str) -> dict[str, str]:
    schema = schema_for(surface)
    rendered = (json.dumps(schema, indent=2, sort_keys=True) + "\n").encode()
    discriminator = {
        "capability": CAPABILITY_SCHEMA_V1,
        "capability-v1": CAPABILITY_SCHEMA_V1,
        "capability-v2": CAPABILITY_SCHEMA_V2,
        "protocol": PROTOCOL_SCHEMA_V1,
        "protocol-v1": PROTOCOL_SCHEMA_V1,
        "protocol-v2": PROTOCOL_SCHEMA_V2,
    }.get(surface, "")
    for name in (
        "schema_version",
        "descriptor_version",
        "plan_version",
        "report_version",
        "request_version",
        "response_version",
        "tck_version",
        "version",
    ):
        value = schema.get("properties", {}).get(name, {}).get("const")
        if isinstance(value, str):
            discriminator = value
            break
    if surface in {"capability", "protocol", "driver", "kernel"}:
        status = "legacy-alias"
        discriminator = discriminator or "legacy-v1"
    elif surface.endswith("-v1"):
        status = "legacy-frozen"
        discriminator = discriminator or "legacy-v1"
    else:
        status = "active"
    return {
        "surface": surface,
        "schema_id": str(schema.get("$id", "")),
        "schema_version": discriminator,
        "status": status,
        "sha256": "sha256:" + sha256(rendered).hexdigest(),
    }


def schema_for(surface: str) -> dict[str, Any]:
    schemas = {
        "capability": capability_schema,
        "capability-v1": capability_schema,
        "capability-v2": capability_schema_v2,
        "protocol": protocol_schema,
        "protocol-v1": protocol_schema,
        "protocol-v2": protocol_schema_v2,
        "kernel": kernel_schema,
        "kernel-v1": kernel_schema,
        "kernel-v2": kernel_schema_v2,
        "driver": driver_schema,
        "driver-v1": driver_schema,
        "driver-v2": driver_schema_v2,
        "trace": trace_schema,
        "commit": commit_schema,
        "conformance-report": conformance_report_schema,
        "scoped-trace": scoped_trace_event_schema,
        "commit-tck-v1": commit_tck_schema,
        "commit-tck-v2": commit_tck_v2_schema,
        "commit-tck-request-v2": commit_tck_request_v2_schema,
        "commit-tck-response-v2": commit_tck_response_v2_schema,
    }
    try:
        return schemas[surface]()
    except KeyError as exc:
        raise ValueError(f"unknown schema surface: {surface}") from exc


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
    if surface in {"capability", "capability-v1", "capability-v2"}:
        schema_version = (
            CAPABILITY_SCHEMA_V2
            if surface == "capability-v2"
            else CAPABILITY_SCHEMA_V1
        )
        manifest = read_capability_manifest(
            _object(payload, "capability manifest"),
            schema_version=schema_version,
        )
        diagnostics = validate_capability_manifest(manifest)
        if diagnostics:
            raise ValueError("; ".join(item.message for item in diagnostics))
        return
    if surface in {"protocol", "protocol-v1", "protocol-v2"}:
        schema_version = (
            PROTOCOL_SCHEMA_V2 if surface == "protocol-v2" else PROTOCOL_SCHEMA_V1
        )
        protocol = read_protocol_manifest(
            _object(payload, "protocol manifest"),
            schema_version=schema_version,
        )
        manifest = CapabilityManifest(
            id="capability:wire-validation",
            name="Wire validation envelope",
            version="0.0.0",
            protocol=protocol,
        )
        diagnostics = validate_capability_manifest(manifest)
        if diagnostics:
            raise ValueError("; ".join(item.message for item in diagnostics))
        return
    if surface in {"driver", "driver-v1"}:
        driver_descriptor_v1_from_dict(_object(payload, "driver descriptor v1"))
        return
    if surface == "driver-v2":
        driver_descriptor_from_dict(_object(payload, "driver descriptor v2"))
        return
    if surface in {"kernel", "kernel-v1"}:
        os_plan_v1_from_dict(_object(payload, "kernel plan v1"))
        return
    if surface == "kernel-v2":
        os_plan_from_dict(_object(payload, "kernel plan v2"))
        return
    if surface == "commit":
        errors = validate_commit_wire_record(payload)
        if errors:
            raise ValueError("; ".join(errors))
        return
    if surface == "trace":
        body = _exact_fields(
            payload,
            {"event_type", "protocol_id", "target", "reason", "lineage"},
            "trace event",
        )
        event = TraceEvent(**body)
        event.validate()
        return
    if surface == "scoped-trace":
        ScopedTraceEvent.from_dict(_object(payload, "scoped trace event"))
        return
    if surface == "conformance-report":
        ConformanceReport.from_dict(_object(payload, "conformance report"))
        return
    if surface == "commit-tck-v1":
        load_commit_tck_vectors(path)
        return
    if surface == "commit-tck-v2":
        load_commit_tck_v2_cases(path)
        return
    if surface == "commit-tck-request-v2":
        CommitTckRequest.from_dict(_object(payload, "Commit TCK request"))
        return
    if surface == "commit-tck-response-v2":
        CommitTckResponse.from_dict(_object(payload, "Commit TCK response"))
        return
    raise ValueError(f"unknown wire surface: {surface}")


def tck_payload(version: str, adapter: str | None, timeout: float) -> dict[str, Any]:
    if version == "v1":
        if adapter:
            raise ValueError("Commit TCK v1 does not expose the JSONL adapter ABI")
        report = run_commit_tck()
        return {
            "output_version": CLI_OUTPUT_VERSION,
            "ok": report.ok,
            "tck_version": report.tck_version,
            "results": [asdict(item) for item in report.results],
        }
    if version != "v2":
        raise ValueError("Commit TCK version is unsupported")
    report = (
        run_commit_tck_v2_jsonl(
            shlex.split(adapter),
            timeout=timeout,
        )
        if adapter
        else run_commit_tck_v2()
    )
    return {
        "output_version": CLI_OUTPUT_VERSION,
        "ok": report.ok,
        "tck_version": report.tck_version,
        "implementation_id": report.implementation_id,
        "protocol_error": report.protocol_error,
        "results": [asdict(item) for item in report.results],
    }


def abi_show_payload(package: str | None = None) -> dict[str, Any]:
    inventory = _load_packaged_abi_inventory()
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
        "inventory": inventory,
    }


def abi_diff_payload(path: str | Path | None = None) -> dict[str, Any]:
    expected = _load_packaged_abi_inventory()
    observed = _load_json(path) if path is not None else build_public_api_inventory()
    differences = public_api_inventory_differences(expected, observed)
    return {
        "report_version": ABI_COMMAND_REPORT_VERSION,
        "ok": not differences,
        "expected_version": expected.get("artifact_version", ""),
        "observed_version": (
            observed.get("artifact_version", "")
            if isinstance(observed, dict)
            else ""
        ),
        "differences": differences,
    }


def _load_packaged_abi_inventory() -> dict[str, Any]:
    resource = resources.files("pheroos.conformance").joinpath(
        "abi",
        "public-python-api-v1.json",
    )
    loaded = json.loads(resource.read_text(encoding="utf-8"))
    return _object(loaded, "public ABI inventory")


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


def _exact_fields(
    value: Any,
    fields: set[str],
    label: str,
) -> dict[str, Any]:
    payload = _object(value, label)
    if set(payload) != fields:
        raise ValueError(f"{label} fields are invalid")
    return payload


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
