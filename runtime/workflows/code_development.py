from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime.workflows.domain_execution import (
    attach_domain_workflow_stop_signals,
    available_tool_names,
    domain_workflow_from_state,
    merge_metadata,
    workflow_agents_by_type,
)


def augment_orchestration_result(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    tools = available_tool_names(result)
    execution_plan = build_execution_plan(
        task=str(state.get("task") or result.get("translated_task") or ""),
        available_tools=tools,
    )
    trace = build_workflow_trace(state, workflow=workflow, execution_plan=execution_plan)
    plan = execution_plan if should_replace_plan(result) else result.get("plan", [])
    updated = {**result, "plan": plan, "domain_workflow": trace}
    return merge_metadata(updated, domain_workflow=trace)


def build_execution_plan(*, task: str, available_tools: set[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if "list_files" in available_tools:
        steps.append(
            {
                "id": "repo-scout",
                "title": "Repo scout",
                "action": "Inspect repository structure and identify likely project conventions before any edit.",
                "tool_calls": [{"name": "list_files", "args": {"path": ".", "pattern": "*", "max_results": 160}}],
            }
        )
    steps.append(
        {
            "id": "patch-plan",
            "title": "Patch plan gate",
            "action": "Create a minimal patch plan and forbidden-file list before coding. Do not write files in this step.",
            "tool_calls": [],
        }
    )
    if "write_file" in available_tools:
        steps.append(
            {
                "id": "coder",
                "title": "Controlled patch mutation",
                "action": (
                    "Apply the minimal patch only if it follows the patch plan and avoids forbidden paths. "
                    "Use only registry tools; do not delete tests to pass."
                ),
            }
        )
    steps.append(
        {
            "id": "diff-interface-security-review",
            "title": "Diff, interface, dependency, and security gates",
            "action": (
                "Review the eventual patch against public API, forbidden path, dependency, security, and test-deletion rules."
            ),
            "tool_calls": [],
        }
    )
    if "run_pytest" in available_tools:
        steps.append(
            {
                "id": "test-runner",
                "title": "Test runner gate",
                "action": "Run the deterministic test gate after patch application.",
                "tool_calls": [{"name": "run_pytest", "args": {"args": ["-q"], "timeout_seconds": 300}}],
            }
        )
    steps.append(
        {
            "id": "regression-judge",
            "title": "Regression judge",
            "action": "Accept, revise, reject, or mark the patch insufficient based on diff, tests, and gate evidence.",
            "tool_calls": [],
        }
    )
    return steps


def build_workflow_trace(
    state: dict[str, Any],
    *,
    workflow: dict[str, Any],
    execution_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    agents = workflow_agents_by_type(state, "code_development_member")
    return {
        "workflow_id": workflow.get("workflow_id") or "code-development",
        "graph_mode": "code_development",
        "domain_nodes": workflow.get("ordered_nodes") or [],
        "graph_nodes": workflow.get("graph_nodes") or [],
        "agents": agents,
        "required_gates": workflow.get("required_gates") or [],
        "committed_candidates": workflow.get("committed_candidates") or [],
        "execution_plan": execution_plan,
        "node_outputs": build_pre_execution_node_outputs(state, execution_plan=execution_plan),
        "guardrails": [
            "coder_agent cannot write before patch_planner_agent output exists",
            "coder_agent cannot bypass test_runner_agent",
            "declared interface/security gates can emit blocking stop-signals for public API breakage",
            "regression_judge_agent cannot accept a patch without diff and test evidence",
        ],
        "writer_policy": workflow.get("writer_policy"),
    }


def augment_execution_result(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    workflow = dict(domain_workflow_from_state(state))
    execution_log = result.get("execution_log") if isinstance(result.get("execution_log"), list) else []
    node_outputs = dict(workflow.get("node_outputs") if isinstance(workflow.get("node_outputs"), dict) else {})
    node_outputs.update(build_post_execution_node_outputs(state, execution_log=execution_log))
    workflow["node_outputs"] = node_outputs
    workflow["code_facts"] = build_code_facts(state, execution_log=execution_log)
    workflow["gate_status"] = code_gate_status(node_outputs)
    updated = {**result, "domain_workflow": workflow}
    return attach_domain_workflow_stop_signals(state, merge_metadata(updated, domain_workflow=workflow))


def build_pre_execution_node_outputs(
    state: dict[str, Any],
    *,
    execution_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    repo_scout = repo_scout_node(state)
    architecture = architecture_mapper_node(state, repo_scout=repo_scout)
    patch_plan = patch_planner_node(state, architecture_map=architecture, execution_plan=execution_plan)
    mutation = controlled_patch_mutation_node(state, patch_plan=patch_plan)
    return {
        "repo_scout": repo_scout,
        "architecture_mapper": architecture,
        "patch_planner": patch_plan,
        "coder": mutation,
    }


def build_post_execution_node_outputs(state: dict[str, Any], *, execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    mutation = controlled_patch_execution_node(execution_log)
    test_runner = test_runner_gate_node(execution_log)
    test_integrity = test_integrity_guard_node(execution_log)
    forbidden_path = forbidden_path_guard_node(execution_log)
    interface_guard = interface_guard_node(state, execution_log=execution_log)
    security = security_scanner_node(state, execution_log=execution_log)
    dependency = dependency_auditor_node(state, execution_log=execution_log)
    regression = regression_judge_node(
        mutation=mutation,
        test_runner=test_runner,
        test_integrity=test_integrity,
        forbidden_path=forbidden_path,
        interface_guard=interface_guard,
        security=security,
        dependency=dependency,
    )
    return {
        "coder": mutation,
        "test_runner": test_runner,
        "test_integrity_guard": test_integrity,
        "forbidden_path_guard": forbidden_path,
        "interface_guard": interface_guard,
        "security_scanner": security,
        "dependency_auditor": dependency,
        "regression_judge": regression,
    }


def repo_scout_node(state: dict[str, Any]) -> dict[str, Any]:
    root = Path.cwd()
    files = {path.name for path in root.iterdir()} if root.exists() else set()
    languages = []
    if "pyproject.toml" in files or "server.py" in files or (root / "runtime").exists():
        languages.append("python")
    if "package.json" in files or (root / "static" / "app.js").exists():
        languages.append("javascript")
    package_managers = []
    if "pyproject.toml" in files:
        package_managers.append("pip")
    if "package.json" in files:
        package_managers.append("npm")
    test_commands = []
    if "pyproject.toml" in files:
        test_commands.append(".venv/bin/pytest -q")
    if "package.json" in files:
        test_commands.append("npm run test:visual")
    return {
        "status": "completed",
        "languages": languages,
        "package_managers": package_managers,
        "test_commands": test_commands,
        "important_files": [name for name in ["AGENTS.md", "pyproject.toml", "package.json"] if name in files],
        "risks": ["do not edit .venv/.local/logs", "respect AGENTS.md model/tool boundaries"],
    }


def architecture_mapper_node(state: dict[str, Any], *, repo_scout: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "completed",
        "public_modules": ["runtime/tool_registry.py", "runtime/os_kernel.py", "runtime/model_gateway.py"],
        "forbidden_paths": [".local/", ".venv/", "logs/", "__pycache__/"],
        "tool_boundary": "runtime/tool_registry.py",
        "model_boundary": "runtime/llm.py",
        "test_commands": repo_scout.get("test_commands", []),
    }


def patch_planner_node(
    state: dict[str, Any],
    *,
    architecture_map: dict[str, Any],
    execution_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "planned",
        "scope": "minimal_patch",
        "task": state.get("task", ""),
        "allowed_after_confirmation": ["read_file", "write_file", "apply_patch", "run_pytest"],
        "forbidden_paths": architecture_map.get("forbidden_paths", []),
        "expected_gates": ["diff_gate", "test_gate", "interface_gate", "security_gate", "dependency_gate"],
        "planned_steps": [step.get("id") for step in execution_plan],
    }


def controlled_patch_mutation_node(state: dict[str, Any], *, patch_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending_patch",
        "requires_patch_plan": True,
        "patch_plan_status": patch_plan.get("status"),
        "policy": "coder_agent may mutate files only after permission grants and patch plan exist",
    }


def controlled_patch_execution_node(execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    coder_entries = [entry for entry in execution_log if str(entry.get("step_id") or "") == "coder"]
    changed_files = changed_files_from_execution_log(coder_entries)
    failed = [entry for entry in coder_entries if entry.get("status") == "failed"]
    if not coder_entries:
        return {
            "status": "not_executed",
            "files_changed": [],
            "requires_patch_plan": True,
            "policy": "Mutation step is omitted unless write_file is permission-granted.",
        }
    return {
        "status": "failed" if failed else "patch_applied" if changed_files else "no_mutation",
        "files_changed": changed_files,
        "requires_patch_plan": True,
        "blocking": bool(failed),
    }


def test_runner_gate_node(execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    test_entries = [entry for entry in execution_log if "test" in str(entry.get("step_id") or "").lower()]
    if not test_entries:
        return {"status": "missing", "passed": False, "blocking": True, "failures": ["test gate did not run"]}
    failed = [entry for entry in test_entries if entry.get("status") == "failed"]
    return {
        "status": "failed" if failed else "passed",
        "passed": not failed,
        "blocking": bool(failed),
        "commands": [entry.get("title") or entry.get("step_id") for entry in test_entries],
        "failures": [entry.get("result") for entry in failed],
    }


def forbidden_path_guard_node(execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    forbidden_prefixes = (".venv/", ".local/", "logs/", "__pycache__/")
    changed_files = changed_files_from_execution_log(execution_log)
    violations = [
        path
        for path in changed_files
        if path.startswith(forbidden_prefixes) or f"/__pycache__/" in path
    ]
    return {
        "status": "failed" if violations else "passed",
        "blocking": bool(violations),
        "violations": violations,
    }


def test_integrity_guard_node(execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    violations = []
    for entry in execution_log:
        for call in entry.get("tool_calls") or []:
            if not isinstance(call, dict) or call.get("name") != "write_file":
                continue
            args = call.get("args") if isinstance(call.get("args"), dict) else {}
            path = str(args.get("path") or "")
            content = args.get("content")
            is_test_path = path.startswith("tests/") or Path(path).name.startswith("test_")
            if is_test_path and isinstance(content, str) and not content.strip():
                violations.append(path)
    return {
        "status": "failed" if violations else "passed",
        "blocking": bool(violations),
        "violations": violations,
    }


def interface_guard_node(state: dict[str, Any], *, execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    changed_files = changed_files_from_execution_log(execution_log)
    public_api_changed = any(path.startswith("runtime/") and path.endswith(".py") for path in changed_files)
    return {
        "status": "failed" if public_api_changed else "passed",
        "public_api_changed": public_api_changed,
        "blocking": public_api_changed,
        "changed_files": changed_files,
    }


def security_scanner_node(state: dict[str, Any], *, execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    serialized = str(execution_log).lower()
    suspicious = [word for word in ["api_key", "password", "secret", "token"] if word in serialized]
    return {
        "status": "failed" if suspicious else "passed",
        "blocking": bool(suspicious),
        "findings": suspicious,
    }


def dependency_auditor_node(state: dict[str, Any], *, execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    changed_files = changed_files_from_execution_log(execution_log)
    dependency_files = [path for path in changed_files if Path(path).name in {"pyproject.toml", "package.json", "package-lock.json"}]
    return {
        "status": "review_required" if dependency_files else "passed",
        "blocking": False,
        "dependency_files_changed": dependency_files,
    }


def regression_judge_node(
    *,
    mutation: dict[str, Any],
    test_runner: dict[str, Any],
    test_integrity: dict[str, Any],
    forbidden_path: dict[str, Any],
    interface_guard: dict[str, Any],
    security: dict[str, Any],
    dependency: dict[str, Any],
) -> dict[str, Any]:
    blockers = [
        name
        for name, gate in {
            "coder": mutation,
            "test_runner": test_runner,
            "test_integrity_guard": test_integrity,
            "forbidden_path_guard": forbidden_path,
            "interface_guard": interface_guard,
            "security_scanner": security,
            "dependency_auditor": dependency,
        }.items()
        if gate.get("blocking")
    ]
    if blockers:
        candidate = "reject_patch"
    elif mutation.get("status") != "patch_applied":
        candidate = "insufficient_context"
    elif test_runner.get("status") == "missing":
        candidate = "insufficient_context"
    elif dependency.get("status") == "review_required":
        candidate = "revise_patch"
    else:
        candidate = "accept_patch"
    return {
        "status": "completed",
        "committed_candidate": candidate,
        "blocking_gates": blockers,
        "reason": "Regression judge requires test, interface, security, and dependency evidence.",
    }


def code_gate_status(node_outputs: dict[str, Any]) -> dict[str, Any]:
    judge = node_outputs.get("regression_judge") if isinstance(node_outputs.get("regression_judge"), dict) else {}
    return {
        "status": judge.get("committed_candidate") or "pending",
        "blocked": judge.get("committed_candidate") in {"reject_patch", "insufficient_context"},
        "blocking_gates": judge.get("blocking_gates", []),
    }


def build_code_facts(state: dict[str, Any], *, execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    repo = repo_scout_node(state)
    architecture = architecture_mapper_node(state, repo_scout=repo)
    changed_files = changed_files_from_execution_log(execution_log)
    return {
        "repo_manifest": repo,
        "architecture_map": architecture,
        "diff_summary": {
            "files_changed": changed_files,
            "added_lines": 0,
            "deleted_lines": 0,
            "public_api_changed": any(path.startswith("runtime/") for path in changed_files),
        },
        "test_results": test_runner_gate_node(execution_log),
    }


def changed_files_from_execution_log(execution_log: list[dict[str, Any]]) -> list[str]:
    changed: list[str] = []
    for entry in execution_log:
        for call in entry.get("tool_calls") or []:
            args = call.get("args") if isinstance(call, dict) else {}
            path = args.get("path") if isinstance(args, dict) else None
            if path and path not in changed:
                changed.append(str(path))
    return changed


def should_replace_plan(result: dict[str, Any]) -> bool:
    plan = result.get("plan")
    if not isinstance(plan, list) or not plan:
        return True
    if len(plan) == 1 and str((plan[0] or {}).get("id") or "") == "direct":
        return True
    return False
