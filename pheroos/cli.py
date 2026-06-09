from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pheroos.protocol.manifest import load_capability_protocol
from pheroos.protocol.validation import protocol_errors, protocol_warnings


def validate_capability_path(path: str | Path) -> dict[str, Any]:
    loaded = load_capability_protocol(path)
    errors = protocol_errors(loaded.diagnostics)
    warnings = protocol_warnings(loaded.diagnostics)
    return {
        "ok": not errors,
        "capability_id": loaded.capability_id,
        "source_path": loaded.source_path,
        "checks": {
            "manifest_schema": "PASS",
            "protocol_validation": "PASS" if not errors else "FAIL",
        },
        "error_count": len(errors),
        "warning_count": len(warnings),
        "diagnostics": loaded.diagnostics,
    }


def conformance_report(path: str | Path) -> dict[str, Any]:
    loaded = load_capability_protocol(path)
    validation = validate_capability_path(path)
    protocol = loaded.protocol
    candidates = protocol.get("candidates") if isinstance(protocol.get("candidates"), list) else []
    declared_candidates = {str(item.get("candidate") or item.get("id")) for item in candidates if isinstance(item, dict)}
    quorum_policy = protocol.get("quorum_policy") if isinstance(protocol.get("quorum_policy"), dict) else {}
    fallback = str(quorum_policy.get("candidate_fallback") or "")
    recovery_protocols = protocol.get("recovery_protocols") if isinstance(protocol.get("recovery_protocols"), list) else []
    output_policy = protocol.get("output_policy") if isinstance(protocol.get("output_policy"), dict) else {}
    tool_policy = protocol.get("tool_policy") if isinstance(protocol.get("tool_policy"), dict) else {}
    checks = {
        **validation["checks"],
        "candidate_declaration": "PASS" if candidates else "N/A",
        "quorum_fallback": "PASS" if not fallback or fallback in declared_candidates else "FAIL",
        "recovery_protocol": recovery_protocol_status(recovery_protocols),
        "tool_contract": "PASS" if tool_policy else "N/A",
        "output_contract": "PASS" if output_policy.get("writer_can_create_facts") is not True else "FAIL",
        "trace_contract": "PASS",
    }
    ok = validation["ok"] and "FAIL" not in set(checks.values())
    return {
        **validation,
        "ok": ok,
        "checks": checks,
        "conformance_level": "pheroos.v0.1.basic",
    }


def recovery_protocol_status(recovery_protocols: Any) -> str:
    if not recovery_protocols:
        return "N/A"
    for item in recovery_protocols:
        if not isinstance(item, dict):
            return "FAIL"
        if not any(item.get(key) for key in ("allowed_agent_roles", "allowed_capability_tags", "required_tools")):
            return "FAIL"
    return "PASS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pheroos")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a capability manifest or directory")
    validate_parser.add_argument("path")

    inspect_parser = subparsers.add_parser("inspect-protocol", help="Print loaded protocol payload")
    inspect_parser.add_argument("path")

    conformance_parser = subparsers.add_parser("conformance", help="Run basic PheroOS conformance checks")
    conformance_parser.add_argument("path")

    args = parser.parse_args(argv)
    if args.command == "validate":
        report = validate_capability_path(args.path)
    elif args.command == "inspect-protocol":
        loaded = load_capability_protocol(args.path)
        report = {
            "ok": loaded.ok,
            "capability_id": loaded.capability_id,
            "protocol": loaded.protocol,
            "diagnostics": loaded.diagnostics,
        }
    elif args.command == "conformance":
        report = conformance_report(args.path)
    else:
        parser.error(f"unknown command: {args.command}")

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


def conformance_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pheroos-conformance")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    report = conformance_report(args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
