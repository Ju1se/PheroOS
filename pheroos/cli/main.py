from __future__ import annotations

import argparse
import json
from typing import Any

from pheroos.conformance import run_conformance, validate_manifest
from pheroos.drivers.schema import driver_schema
from pheroos.kernel.schema import kernel_schema
from pheroos.protocol.schema import capability_schema, protocol_schema
from pheroos.trace.schema import trace_schema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pheroos")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("path")

    conformance_parser = sub.add_parser("conformance")
    conformance_parser.add_argument("path")

    schema_parser = sub.add_parser("schema")
    schema_sub = schema_parser.add_subparsers(dest="schema_command", required=True)
    export_parser = schema_sub.add_parser("export")
    export_parser.add_argument("surface", choices=["capability", "protocol", "kernel", "driver", "trace"])

    args = parser.parse_args(argv)
    if args.command == "validate":
        return emit_report(validate_manifest(args.path).to_dict())
    if args.command == "conformance":
        return emit_report(run_conformance(args.path).to_dict())
    if args.command == "schema" and args.schema_command == "export":
        return emit_report(schema_for(args.surface))
    parser.error("unknown command")
    return 2


def emit_report(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok", True) is not False else 1


def schema_for(surface: str) -> dict[str, Any]:
    if surface == "capability":
        return capability_schema()
    if surface == "protocol":
        return protocol_schema()
    if surface == "kernel":
        return kernel_schema()
    if surface == "driver":
        return driver_schema()
    if surface == "trace":
        return trace_schema()
    raise ValueError(f"unknown schema surface: {surface}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
