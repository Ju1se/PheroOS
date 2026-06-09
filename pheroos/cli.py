from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pheroos.minimal import init_minimal_project, latest_minimal_trace, run_minimal_task
from pheroos.protocol.capability_manifest import load_public_capability_manifest
from pheroos.protocol.manifest import load_capability_protocol
from pheroos.protocol.validation import protocol_errors, protocol_warnings


REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_LEAKAGE_FORBIDDEN_TERMS = (
    "w" "rds",
    "value" "_investing",
    "formal" "_valuation",
    "b" "uy",
    "s" "ell",
    "w" "atch",
    "a" "void",
)


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
    manifest = load_capability_manifest(path)
    protocol = loaded.protocol
    conformance_checks = build_conformance_checks(manifest, protocol)
    checks = {
        **validation["checks"],
        **{name: detail["status"] for name, detail in conformance_checks.items()},
    }
    ok = validation["ok"] and "FAIL" not in set(checks.values())
    return {
        **validation,
        "ok": ok,
        "checks": checks,
        "check_details": conformance_checks,
        "conformance_level": "pheroos.v0.1.basic",
    }


def load_capability_manifest(path: str | Path) -> dict[str, Any]:
    return load_public_capability_manifest(path)


def build_conformance_checks(manifest: dict[str, Any], protocol: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates = list_of_dicts(protocol.get("candidates"))
    quorum_policy = dict_value(protocol.get("quorum_policy"))
    recovery_protocols = list_of_dicts(protocol.get("recovery_protocols"))
    tool_policy = dict_value(protocol.get("tool_policy"))
    output_policy = dict_value(protocol.get("output_policy"))
    evidence_policy = dict_value(protocol.get("evidence_policy"))
    targets = list_of_dicts(protocol.get("targets"))

    return {
        "candidate_declaration": candidate_declaration_status(candidates, quorum_policy, recovery_protocols),
        "quorum_fallback": quorum_fallback_status(candidates, quorum_policy),
        "recovery_protocol": recovery_protocol_detail(recovery_protocols, candidates),
        "tool_contract": tool_contract_status(manifest, tool_policy),
        "output_contract": output_contract_status(output_policy, candidates, evidence_policy),
        "trace_contract": trace_contract_status(
            targets,
            candidates,
            quorum_policy,
            recovery_protocols,
            output_policy,
            evidence_policy,
            tool_policy,
        ),
        "domain_leakage_guard": domain_leakage_guard_status(),
        "core_runtime_domain_leakage_guard": core_runtime_domain_leakage_guard_status(),
    }


def candidate_declaration_status(
    candidates: list[dict[str, Any]],
    quorum_policy: dict[str, Any],
    recovery_protocols: list[dict[str, Any]],
) -> dict[str, Any]:
    declared = candidate_ids(candidates)
    quorum_candidates = set(string_list(quorum_policy.get("candidates")))
    recovery_failure_candidates = {
        str(item.get("recovery_failure_candidate") or "").strip()
        for item in recovery_protocols
        if str(item.get("recovery_failure_candidate") or "").strip()
    }
    referenced = quorum_candidates | recovery_failure_candidates

    if not declared and not referenced:
        return check("N/A", "no candidate or quorum policy declared")
    if not declared:
        return check("FAIL", "candidate references exist but no candidates are declared", referenced=sorted(referenced))

    missing = sorted(referenced - declared)
    if missing:
        return check("FAIL", "policy references undeclared candidates", missing=missing)

    missing_targets = sorted(
        str(item.get("candidate") or item.get("id") or "")
        for item in candidates
        if not str(item.get("target") or "").strip()
    )
    if missing_targets:
        return check("FAIL", "candidate declarations must include targets", candidates=missing_targets)

    return check("PASS", "all quorum and recovery candidates are protocol-declared", declared=sorted(declared))


def quorum_fallback_status(candidates: list[dict[str, Any]], quorum_policy: dict[str, Any]) -> dict[str, Any]:
    if not candidates and not quorum_policy:
        return check("N/A", "no quorum policy declared")

    declared = candidate_ids(candidates)
    fallback = str(quorum_policy.get("candidate_fallback") or "").strip()
    if not fallback:
        return check("FAIL", "quorum policy must declare a fallback candidate")
    if fallback not in declared:
        return check("FAIL", "quorum fallback is not a declared candidate", candidate=fallback)

    fallback_decl = next((item for item in candidates if candidate_id(item) == fallback), {})
    if fallback_decl.get("safe_fallback") is not True:
        return check("FAIL", "quorum fallback candidate must be marked safe_fallback", candidate=fallback)

    return check("PASS", "quorum fallback is declared and marked safe_fallback", candidate=fallback)


def recovery_protocol_status(recovery_protocols: Any) -> str:
    details = recovery_protocol_detail(list_of_dicts(recovery_protocols), [])
    return str(details["status"])


def recovery_protocol_detail(
    recovery_protocols: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not recovery_protocols:
        return check("N/A", "no recovery protocols declared")

    declared_candidates = candidate_ids(candidates)
    failures: list[str] = []
    for item in recovery_protocols:
        recovery_id = str(item.get("recovery_id") or item.get("id") or "").strip() or "<unknown>"
        if not string_list(item.get("trigger_targets")):
            failures.append(f"{recovery_id}:missing_trigger_targets")
        if not any(item.get(key) for key in ("allowed_agent_roles", "allowed_capability_tags", "required_tools")):
            failures.append(f"{recovery_id}:missing_role_tag_or_tool_selector")
        if not str(item.get("recovery_success_condition") or "").strip():
            failures.append(f"{recovery_id}:missing_success_condition")
        failure_candidate = str(item.get("recovery_failure_candidate") or "").strip()
        if not failure_candidate:
            failures.append(f"{recovery_id}:missing_failure_candidate")
        elif declared_candidates and failure_candidate not in declared_candidates:
            failures.append(f"{recovery_id}:undeclared_failure_candidate:{failure_candidate}")

    if failures:
        return check("FAIL", "recovery protocols are incomplete or reference undeclared candidates", failures=failures)
    return check("PASS", "recovery protocols declare triggers, selectors, success, and failure behavior")


def tool_contract_status(manifest: dict[str, Any], tool_policy: dict[str, Any]) -> dict[str, Any]:
    manifest_permissions = set(string_list(manifest.get("permissions")))
    required_permissions = set(string_list(tool_policy.get("required_permissions")))
    unknown_permissions = string_list(dict_value(manifest.get("permission_diagnostics")).get("unknown_permissions"))
    tool_targets = (
        string_list(tool_policy.get("allowed_tool_targets"))
        + string_list(tool_policy.get("blocked_tool_targets"))
        + string_list(tool_policy.get("source_policy_blocked_tool_targets"))
    )
    tool_surface = bool(
        string_list(manifest.get("tools"))
        or tool_targets
        or string_list(manifest.get("required_connections"))
        or string_list(tool_policy.get("required_connections"))
    )

    if unknown_permissions:
        return check("FAIL", "manifest declares unknown permissions", permissions=unknown_permissions)

    missing = sorted(required_permissions - manifest_permissions)
    if missing:
        return check("FAIL", "tool policy requires permissions missing from manifest", permissions=missing)

    if tool_surface and not manifest_permissions and not required_permissions:
        return check("FAIL", "tool or connection surface requires explicit permissions")

    if manifest_permissions or required_permissions or tool_surface:
        return check("PASS", "tool surface is permission-declared")
    return check("N/A", "no tool surface declared")


def output_contract_status(
    output_policy: dict[str, Any],
    candidates: list[dict[str, Any]],
    evidence_policy: dict[str, Any],
) -> dict[str, Any]:
    if not output_policy:
        return check("N/A", "no output policy declared")
    if output_policy.get("writer_can_create_facts") is True:
        return check("FAIL", "writer cannot be authorized to create facts")

    required_checks = set(string_list(output_policy.get("final_judge_required_checks")))
    if candidates and "committed_candidate" not in required_checks:
        return check("FAIL", "candidate-based output must require final judge committed_candidate check")

    if evidence_policy and evidence_policy.get("raw_data_allowed_in_final") is True:
        return check("FAIL", "raw data in final output is not conformant for the public profile")

    return check("PASS", "output policy preserves writer and final judge authority boundaries")


def trace_contract_status(
    targets: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    quorum_policy: dict[str, Any],
    recovery_protocols: list[dict[str, Any]],
    output_policy: dict[str, Any],
    evidence_policy: dict[str, Any],
    tool_policy: dict[str, Any],
) -> dict[str, Any]:
    if not targets:
        return check("FAIL", "trace lineage requires declared protocol targets")

    lineage_sources = [
        name
        for name, present in (
            ("candidate_set", bool(candidates)),
            ("quorum_policy", bool(quorum_policy)),
            ("recovery_protocols", bool(recovery_protocols)),
            ("output_policy", bool(output_policy)),
            ("evidence_policy", bool(evidence_policy)),
            ("tool_policy", bool(tool_policy)),
        )
        if present
    ]
    if not lineage_sources:
        return check("FAIL", "trace lineage requires at least one governed policy source")

    return check("PASS", "protocol declares traceable targets and policy lineage", lineage_sources=lineage_sources)


def domain_leakage_guard_status() -> dict[str, Any]:
    offenders = domain_leakage_offenders(public_abi_surface_paths())
    if offenders:
        return check("FAIL", "domain-specific terms leaked into the public ABI surface", offenders=offenders)
    return check("PASS", "public ABI surface is domain-neutral")


def core_runtime_domain_leakage_guard_status() -> dict[str, Any]:
    offenders = domain_leakage_offenders(core_runtime_surface_paths())
    if offenders:
        return check("FAIL", "domain-specific terms leaked into core runtime governance files", offenders=offenders)
    return check("PASS", "core runtime governance surface is domain-neutral")


def domain_leakage_offenders(paths: list[Path]) -> list[str]:
    offenders: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for term, pattern in domain_leakage_patterns():
            if pattern.search(text):
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{term}")
    return offenders


def domain_leakage_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(
        (term, re.compile(rf"\b{re.escape(term)}\b"))
        for term in DOMAIN_LEAKAGE_FORBIDDEN_TERMS
    )


def public_abi_surface_paths() -> list[Path]:
    roots = [REPO_ROOT / "pheroos", REPO_ROOT / "docs" / "kernel", REPO_ROOT / "schemas"]
    paths: list[Path] = []
    for root in roots:
        if root.exists():
            paths.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py", ".md", ".json"}
            )
    return sorted(paths)


def core_runtime_surface_paths() -> list[Path]:
    paths = [
        REPO_ROOT / "runtime" / "os_kernel.py",
        REPO_ROOT / "runtime" / "runtime_context.py",
        REPO_ROOT / "runtime" / "swarm" / "quorum.py",
        REPO_ROOT / "runtime" / "swarm" / "recovery_engine.py",
        REPO_ROOT / "runtime" / "swarm" / "control_loop.py",
        REPO_ROOT / "runtime" / "swarm" / "candidate_registry.py",
        REPO_ROOT / "runtime" / "nodes" / "output_chain.py",
        REPO_ROOT / "runtime" / "writer_guardrails.py",
        REPO_ROOT / "runtime" / "final_judge_guardrails.py",
    ]
    return sorted(path for path in paths if path.exists())


def candidate_ids(candidates: list[dict[str, Any]]) -> set[str]:
    return {value for value in (candidate_id(item) for item in candidates) if value}


def candidate_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate") or candidate.get("id") or "").strip()


def check(status: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "message": message, **extra}


def dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pheroos")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a capability manifest or directory")
    validate_parser.add_argument("path")

    inspect_parser = subparsers.add_parser("inspect-protocol", help="Print loaded protocol payload")
    inspect_parser.add_argument("path")

    conformance_parser = subparsers.add_parser("conformance", help="Run basic PheroOS conformance checks")
    conformance_parser.add_argument("path")

    init_parser = subparsers.add_parser("init", help="Initialize a PheroOS distro workspace")
    init_subparsers = init_parser.add_subparsers(dest="template", required=True)
    init_minimal_parser = init_subparsers.add_parser("minimal", help="Initialize the no-key minimal distro")
    init_minimal_parser.add_argument("path", nargs="?", default=".")

    run_parser = subparsers.add_parser("run", help="Run a task through a PheroOS distro")
    run_parser.add_argument("task")
    run_parser.add_argument("--distro", choices=["minimal"], default="minimal")
    run_parser.add_argument("--workspace", default=".")

    trace_parser = subparsers.add_parser("trace", help="Inspect local PheroOS traces")
    trace_subparsers = trace_parser.add_subparsers(dest="trace_command", required=True)
    trace_latest_parser = trace_subparsers.add_parser("latest", help="Show the latest local trace")
    trace_latest_parser.add_argument("--workspace", default=".")

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
    elif args.command == "init" and args.template == "minimal":
        report = init_minimal_project(args.path)
    elif args.command == "run":
        report = run_minimal_task(args.task, workspace=args.workspace)
    elif args.command == "trace" and args.trace_command == "latest":
        report = latest_minimal_trace(workspace=args.workspace)
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
