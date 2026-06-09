from __future__ import annotations

import argparse
import json
from typing import Any

from pheroos.conformance import run_conformance, validate_manifest
from pheroos.protocol.schema import capability_schema, protocol_schema


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
    export_parser.add_argument("surface", choices=["protocol", "kernel", "driver", "trace"])

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
    if surface == "protocol":
        return protocol_schema()
    if surface == "kernel":
        return simple_surface_schema("kernel")
    if surface == "driver":
        return simple_surface_schema("driver")
    if surface == "trace":
        return simple_surface_schema("trace")
    raise ValueError(f"unknown schema surface: {surface}")


def simple_surface_schema(surface: str) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://pheroos.dev/schemas/{surface}.schema.json",
        "type": "object",
        "additionalProperties": True,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
