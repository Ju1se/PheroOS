from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs/protocol/baseline-output-v2.md"
MANIFEST_PATH = ROOT / "pheroos/protocol/authority_manifest_v2.py"
SCHEMA_PATH = ROOT / "pheroos/protocol/authority_schema_v2.py"
CONTRACTS_PATH = ROOT / "pheroos/governance/_baseline_output_v2/contracts.py"
OPERATIONS_PATH = ROOT / "pheroos/governance/_baseline_output_v2/operations.py"
JOURNEY_PATH = ROOT / "pheroos/governance/_baseline_output_v2/journey.py"
FACADE_PATH = ROOT / "pheroos/governance/baseline_output_v2.py"
TRACE_AUTHORITY_PATH = ROOT / "pheroos/trace/_contracts/authority.py"
TRACE_V1_PATH = ROOT / "pheroos/trace/commit_contracts.py"
CONFORMANCE_PATH = ROOT / "pheroos/conformance/checks/baseline_output_v2_contract.py"


EXPECTED_REQUEST_FIELDS = (
    "domain_root",
    "scope_ref",
    "run_ref",
    "request_ref",
    "output_transition_id",
    "manifest",
    "target_ref",
    "action_ref",
    "proposed_candidate_ref",
    "verified_signals",
    "stop_resolutions",
    "output_payload",
    "observed_epoch",
    "manifest_stream_ref",
    "evidence_stream_ref",
    "stop_stream_ref",
    "decision_stream_ref",
    "permission_stream_ref",
    "output_stream_ref",
    "output_payload_root",
    "schema",
    "canonical_version",
    "request_root",
)

EXPECTED_PERMISSION_FIELDS = (
    "domain_root",
    "scope_ref",
    "run_ref",
    "request_ref",
    "request_root",
    "permission_transition_id",
    "permission_stream_ref",
    "manifest_root",
    "output_policy_root",
    "evidence_root",
    "stop_root",
    "decision_root",
    "target_ref",
    "candidate_ref",
    "action_ref",
    "effect",
    "terminal_status",
    "output_payload_root",
    "disposition",
    "issued_epoch",
    "expires_at_epoch",
    "grant_ref",
    "grant_root",
    "grant_binding_ref",
    "schema",
    "canonical_version",
    "permission_root",
)

EXPECTED_RESULT_FIELDS = (
    "domain_root",
    "scope_ref",
    "run_ref",
    "request_ref",
    "request_root",
    "output_transition_id",
    "output_payload_root",
    "terminal_status",
    "candidate_ref",
    "delivery_disposition",
    "action_disposition",
    "permission_root",
    "authorization",
    "commit_attempt",
    "result_root",
    "schema",
    "canonical_version",
)

EXPECTED_EVENTS = (
    "baseline_manifest_activated",
    "baseline_evidence_qualified",
    "baseline_stop_resolved",
    "baseline_decision_evaluated",
    "baseline_action_permission_issued",
    "baseline_output_committed",
)

EXPECTED_PUBLIC_API = (
    "ACTION_PERMISSION_SCHEMA_V2",
    "BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2",
    "BASELINE_DECISION_STATE_SCHEMA_V2",
    "BASELINE_EVIDENCE_STATE_SCHEMA_V2",
    "BASELINE_MANIFEST_STATE_SCHEMA_V2",
    "BASELINE_OUTPUT_REQUEST_SCHEMA_V2",
    "BASELINE_OUTPUT_RESULT_SCHEMA_V2",
    "BASELINE_OUTPUT_STATE_SCHEMA_V2",
    "BASELINE_STOP_STATE_SCHEMA_V2",
    "ActionPermissionDispositionV2",
    "ActionPermissionV2",
    "BaselineOutputActionDispositionV2",
    "BaselineOutputDeliveryDispositionV2",
    "BaselineOutputRequestV2",
    "BaselineOutputResultV2",
    "BaselineOutputTerminalStatusV2",
    "baseline_action_permission_stream_ref_v2",
    "baseline_decision_stream_ref_v2",
    "baseline_evidence_stream_ref_v2",
    "baseline_manifest_stream_ref_v2",
    "baseline_output_result_root_v2",
    "baseline_output_stream_ref_v2",
    "baseline_stop_stream_ref_v2",
    "baseline_verified_signal_proposal_root_v2",
    "evaluate_and_commit_baseline_output_v2",
    "evaluate_and_commit_governed_baseline_output_v2",
    "issue_action_permission_v2",
    "open_baseline_output_authority_session_v2",
    "recover_baseline_output_result_v2",
)


def _text() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _between(marker: str) -> str:
    text = _text()
    start = f"<!-- {marker}:start -->"
    end = f"<!-- {marker}:end -->"
    assert text.count(start) == 1
    assert text.count(end) == 1
    return text.split(start, 1)[1].split(end, 1)[0]


def _code_lines(marker: str, language: str = "text") -> tuple[str, ...]:
    section = _between(marker)
    match = re.fullmatch(
        rf"\s*```{language}\s*\n(.*?)\n```\s*",
        section,
        re.DOTALL,
    )
    assert match is not None
    return tuple(line for line in match.group(1).splitlines() if line)


def _table(marker: str) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for line in _between(marker).splitlines():
        if not line.startswith("|"):
            continue
        cells = tuple(
            item.strip().replace("`", "") for item in line.strip("|").split("|")
        )
        if cells and all(set(item) <= {"-", ":"} for item in cells):
            continue
        rows.append(cells)
    assert len(rows) >= 2
    return tuple(rows[1:])


def _assignment(path: Path, name: str) -> Any:
    for node in _module(path).body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == name for target in targets
        ):
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in {"frozenset", "set", "tuple"}
            and len(value.args) == 1
        ):
            return ast.literal_eval(value.args[0])
        return ast.literal_eval(value)
    raise AssertionError(f"missing assignment {name} in {path}")


def _class_fields(path: Path, class_name: str) -> tuple[str, ...]:
    for node in _module(path).body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return tuple(
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            )
    raise AssertionError(f"missing class {class_name} in {path}")


def _class_methods(path: Path, class_name: str) -> set[str]:
    for node in _module(path).body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError(f"missing class {class_name} in {path}")


def _function(path: Path, name: str) -> ast.FunctionDef:
    for node in _module(path).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing function {name} in {path}")


def _enum_values(path: Path, class_name: str) -> tuple[str, ...]:
    for node in _module(path).body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return tuple(
                ast.literal_eval(item.value)
                for item in node.body
                if isinstance(item, ast.Assign)
                and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
            )
    raise AssertionError(f"missing enum {class_name} in {path}")


def test_explicit_v3_activation_and_exact_versions_are_frozen() -> None:
    registry = dict(_table("baseline-output-v2-version-registry"))

    assert registry == {
        "Protocol semantics": "pheroos.protocol.v2",
        "Protocol schema selector": "pheroos-protocol-schema-v3",
        "Protocol schema file": "protocol-v3.schema.json",
        "Protocol schema $id": "https://pheroos.dev/schemas/protocol-v3.schema.json",
        "Capability schema selector": "pheroos-capability-schema-v3",
        "Capability schema file": "capability-v3.schema.json",
        "Capability schema $id": (
            "https://pheroos.dev/schemas/capability-v3.schema.json"
        ),
        "Authority policy": "pheroos-scoped-authority-policy-v2",
        "Local authority profile": "pheroos-scoped-authority-local-v2",
        "Authenticated authority profile": (
            "pheroos-scoped-authority-authenticated-v2"
        ),
        "Authority wire": "pheroos-authority-wire-v2",
        "Authority canonicalization": "pheroos-authority-canonical-v2",
        "Authority ledger": "pheroos-governance-authority-ledger-v2",
        "Authority StateStore": "pheroos-governance-state-store-v2",
        "Authority read-set": "pheroos-governance-authority-read-set-v2",
        "Authority Trace batch": "pheroos-governance-trace-batch-v2",
        "Baseline output policy": "pheroos-baseline-output-policy-v2",
        "Baseline Conformance": "pheroos-baseline-output-conformance-v2",
    }
    assert (
        _assignment(MANIFEST_PATH, "PROTOCOL_VERSION_V2")
        == registry["Protocol semantics"]
    )
    assert (
        _assignment(SCHEMA_PATH, "PROTOCOL_SCHEMA_V3")
        == registry["Protocol schema selector"]
    )
    assert (
        _assignment(SCHEMA_PATH, "CAPABILITY_SCHEMA_V3")
        == registry["Capability schema selector"]
    )
    assert (
        _assignment(SCHEMA_PATH, "PROTOCOL_SCHEMA_V3_ID")
        == registry["Protocol schema $id"]
    )
    assert (
        _assignment(SCHEMA_PATH, "CAPABILITY_SCHEMA_V3_ID")
        == registry["Capability schema $id"]
    )
    assert "Readers must not infer v3 from object shape." in _text()
    assert "no v2 operation silently falls back" in _text()


def test_schema_registry_matches_every_governance_identifier() -> None:
    registry = dict(_table("baseline-output-v2-schema-registry"))
    expected_constants = (
        "BASELINE_OUTPUT_REQUEST_SCHEMA_V2",
        "ACTION_PERMISSION_SCHEMA_V2",
        "BASELINE_OUTPUT_RESULT_SCHEMA_V2",
        "BASELINE_MANIFEST_STATE_SCHEMA_V2",
        "BASELINE_EVIDENCE_STATE_SCHEMA_V2",
        "BASELINE_STOP_STATE_SCHEMA_V2",
        "BASELINE_DECISION_STATE_SCHEMA_V2",
        "BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2",
        "BASELINE_OUTPUT_STATE_SCHEMA_V2",
    )

    assert tuple(registry) == expected_constants
    for constant in expected_constants:
        assert registry[constant] == _assignment(CONTRACTS_PATH, constant)
        assert registry[constant].startswith("pheroos-governance-")
    for stale in (
        "`pheroos-baseline-output-request-v2`",
        "`pheroos-action-permission-v2`",
        "`pheroos-baseline-output-result-v2`",
    ):
        assert stale not in _text()


def test_protocol_action_policy_and_safety_invariants_match_owner() -> None:
    action_fields = _code_lines("baseline-output-v2-action-policy-fields")
    output_fields = _code_lines("baseline-output-v2-output-policy-fields")

    assert action_fields == (
        "action_ref",
        "effect",
        "target",
        "allowed_outcomes",
    )
    assert output_fields == ("policy_version", "decision_mode", "actions")
    assert _class_fields(MANIFEST_PATH, "BaselineOutputActionPolicyV2") == action_fields
    assert _class_fields(MANIFEST_PATH, "BaselineOutputPolicyV2") == output_fields
    assert _assignment(MANIFEST_PATH, "SUPPORTED_BASELINE_OUTPUT_EFFECTS_V2") == {
        "publish",
        "execute",
    }
    assert _assignment(MANIFEST_PATH, "SUPPORTED_BASELINE_ACTION_OUTCOMES_V2") == {
        "evidence_commit",
        "safe_fallback",
    }
    assert _assignment(MANIFEST_PATH, "SUPPORTED_BASELINE_DECISION_MODES_V2") == {
        "quorum",
        "direct_governance",
    }
    assert "every action target equals `quorum_policy.target`" in _text()
    assert "baseline output actions must use the quorum fallback target" in (
        MANIFEST_PATH.read_text(encoding="utf-8")
    )
    policy_section = _between("baseline-output-v2-output-policy-fields")
    for stale in (
        "allowed_actions",
        "actionable_terminal_statuses",
        "requires_committed_candidate",
        "requires_evidence_contract",
        "writer_may_create_facts",
    ):
        assert stale not in policy_section


def test_public_facade_and_entrypoint_signatures_are_exact() -> None:
    assert _code_lines("baseline-output-v2-public-api") == EXPECTED_PUBLIC_API
    assert tuple(_assignment(FACADE_PATH, "__all__")) == EXPECTED_PUBLIC_API
    entrypoints = _between("baseline-output-v2-entrypoints")

    expected = {
        "open_baseline_output_authority_session_v2": (
            ("capability", "request", "operation"),
            (),
        ),
        "issue_action_permission_v2": (("request",), ("authority_session",)),
        "evaluate_and_commit_baseline_output_v2": (
            ("request",),
            ("authority_session",),
        ),
        "recover_baseline_output_result_v2": (
            ("request",),
            ("state_reader",),
        ),
    }
    for name, (positional, keyword_only) in expected.items():
        node = _function(OPERATIONS_PATH, name)
        assert tuple(arg.arg for arg in node.args.args) == positional
        assert tuple(arg.arg for arg in node.args.kwonlyargs) == keyword_only
        assert f"def {name}(" in entrypoints
    governed = _function(
        JOURNEY_PATH,
        "evaluate_and_commit_governed_baseline_output_v2",
    )
    assert tuple(arg.arg for arg in governed.args.args) == (
        "store",
        "domain",
        "grant",
        "activation_transition_id",
        "activation_observed_epoch",
        "request",
    )
    assert tuple(arg.arg for arg in governed.args.kwonlyargs) == (
        "verified_signal_requests",
        "verifier",
    )
    assert "def evaluate_and_commit_governed_baseline_output_v2(" in entrypoints
    for name in (
        "issue_action_permission_v2",
        "evaluate_and_commit_baseline_output_v2",
    ):
        node = _function(OPERATIONS_PATH, name)
        assert len(node.args.kw_defaults) == 1
        assert isinstance(node.args.kw_defaults[0], ast.Constant)
        assert node.args.kw_defaults[0].value is None
    assert entrypoints.count("authority_session: object = None") == 2
    assert "state_reader: GovernanceStateReaderV2" in entrypoints
    for stale_signature in (
        "publication_permission:",
        "allowed:",
        "decision:",
        "permission: ActionPermissionV2",
        "permission: bool",
    ):
        assert stale_signature not in entrypoints
    assert "It accepts no\ncaller-supplied permission" in _text()


def test_record_fields_match_implementation_and_exclude_stale_draft_fields() -> None:
    documented = {
        "BaselineOutputRequestV2": _code_lines("baseline-output-v2-request-fields"),
        "ActionPermissionV2": _code_lines("baseline-output-v2-permission-fields"),
        "BaselineOutputResultV2": _code_lines("baseline-output-v2-result-fields"),
    }
    assert documented == {
        "BaselineOutputRequestV2": EXPECTED_REQUEST_FIELDS,
        "ActionPermissionV2": EXPECTED_PERMISSION_FIELDS,
        "BaselineOutputResultV2": EXPECTED_RESULT_FIELDS,
    }
    for class_name, fields in documented.items():
        assert _class_fields(CONTRACTS_PATH, class_name) == fields
        assert {"to_dict", "from_dict", "canonical_bytes", "root"} <= _class_methods(
            CONTRACTS_PATH,
            class_name,
        )

    stale_fields = {
        "capability_manifest",
        "transition_id",
        "manifest_schema_version",
        "direct_candidate_ref",
        "evidence_records",
        "stop_resolution",
        "permission_ref",
        "output_payload_fingerprint",
        "allowed",
        "reason_refs",
        "delivery_eligible",
        "action_authorization_ref",
    }
    assert stale_fields.isdisjoint(documented["BaselineOutputRequestV2"])
    assert stale_fields.isdisjoint(documented["ActionPermissionV2"])
    assert stale_fields.isdisjoint(documented["BaselineOutputResultV2"])
    assert "permission_root" in documented["BaselineOutputResultV2"]
    assert "exact `ScopedProtocolManifestV2`" in _text()


def test_nested_proposals_and_signal_root_bind_all_authority_fields() -> None:
    signal_fields = _code_lines("baseline-output-v2-verified-signal-fields")
    stop_fields = _code_lines("baseline-output-v2-stop-fields")

    assert signal_fields == (
        "candidate_ref",
        "evidence_root",
        "provenance_ref",
        "signal_ref",
        "signal_root",
        "signal_transition_id",
        "source_ref",
    )
    assert set(signal_fields) == _assignment(CONTRACTS_PATH, "_SIGNAL_FIELDS")
    assert stop_fields == (
        "action_ref",
        "blocked",
        "provenance_ref",
        "reason_ref",
    )
    assert set(stop_fields) == _assignment(CONTRACTS_PATH, "_STOP_FIELDS")

    helper = _function(CONTRACTS_PATH, "baseline_verified_signal_proposal_root_v2")
    assert not helper.args.args
    assert tuple(arg.arg for arg in helper.args.kwonlyargs) == (
        "domain_root",
        "scope_ref",
        "run_ref",
        "target_ref",
        "candidate_ref",
        "signal_ref",
        "evidence_root",
        "provenance_ref",
        "source_ref",
    )
    text = _text()
    assert (
        "binds domain, scope, run, target, candidate, signal, evidence, provenance"
        in text
    )
    assert "cannot reinterpret the already committed\nverified signal" in text


def test_six_derived_streams_and_full_read_sets_are_exact() -> None:
    streams = _table("baseline-output-v2-stream-bindings")
    assert streams == (
        ("manifest_stream_ref", "baseline-manifest", "scope_ref, manifest.id"),
        (
            "evidence_stream_ref",
            "baseline-evidence",
            "scope_ref, run_ref, target_ref",
        ),
        ("stop_stream_ref", "baseline-stop", "scope_ref, run_ref, target_ref"),
        (
            "decision_stream_ref",
            "baseline-decision",
            "scope_ref, run_ref, target_ref",
        ),
        (
            "permission_stream_ref",
            "baseline-action-permission",
            "scope_ref, run_ref, target_ref, action_ref",
        ),
        (
            "output_stream_ref",
            "baseline-output",
            "scope_ref, run_ref, target_ref, action_ref",
        ),
    )
    read_sets = _table("baseline-output-v2-read-sets")
    assert read_sets == (
        ("Manifest", "own, permission issuer grant, domain lifecycle"),
        (
            "Evidence",
            "own, manifest, each verified-signal stream, permission issuer grant, domain lifecycle",
        ),
        ("Stop", "own, manifest, permission issuer grant, domain lifecycle"),
        (
            "Decision",
            "own, manifest, evidence, stop, permission issuer grant, domain lifecycle",
        ),
        (
            "Permission",
            "own, manifest, evidence, stop, decision, permission issuer grant, domain lifecycle",
        ),
        (
            "Output",
            "own, manifest, evidence, stop, decision, permission, permission issuer grant if distinct, output authorizer grant, domain lifecycle",
        ),
    )
    text = _text()
    assert (
        "When both sessions use the same grant, the grant dependency appears once."
        in text
    )
    assert "every output read-set dependency other than the output write stream" in text


def test_permission_and_result_enums_freeze_delivery_action_separation() -> None:
    assert _enum_values(CONTRACTS_PATH, "ActionPermissionDispositionV2") == (
        "authorized",
        "denied",
    )
    assert _enum_values(CONTRACTS_PATH, "BaselineOutputTerminalStatusV2") == (
        "evidence_commit",
        "safe_fallback",
        "blocked",
        "invalid",
        "finality_unavailable",
    )
    assert _enum_values(CONTRACTS_PATH, "BaselineOutputDeliveryDispositionV2") == (
        "deliverable",
        "retry_required",
    )
    assert _enum_values(CONTRACTS_PATH, "BaselineOutputActionDispositionV2") == (
        "authorized",
        "denied",
    )

    matrix = _table("baseline-output-v2-terminal-matrix")
    assert tuple(row[0] for row in matrix) == (
        "evidence_commit",
        "safe_fallback",
        "blocked",
        "invalid",
        "finality_unavailable",
        "None",
    )
    assert tuple(row[1] for row in matrix) == (
        "deliverable",
        "deliverable",
        "deliverable",
        "deliverable",
        "deliverable",
        "retry_required",
    )
    assert matrix[2][3] == "always denied"
    assert "diagnostic envelope, not a committed business output" in matrix[3][2]
    assert "diagnostic envelope, not a committed business output" in matrix[4][2]
    assert "A retry has neither terminal status nor\ncandidate" in _text()


def test_events_match_protocol_trace_conformance_and_keep_v1_isolated() -> None:
    documented = _code_lines("baseline-output-v2-trace-events")

    assert documented == EXPECTED_EVENTS
    assert _assignment(
        MANIFEST_PATH, "REQUIRED_BASELINE_OUTPUT_TRACE_EVENTS_V2"
    ) == set(EXPECTED_EVENTS)
    assert _assignment(TRACE_AUTHORITY_PATH, "_BASELINE_OUTPUT_EVENT_TYPES") == set(
        EXPECTED_EVENTS
    )
    assert _assignment(CONFORMANCE_PATH, "_REQUIRED_BASELINE_EVENTS") == set(
        EXPECTED_EVENTS
    )
    assert _assignment(TRACE_V1_PATH, "_PERMISSION") == {"action_permission_issued"}
    assert "action_permission_issued" not in documented
    for event_type in EXPECTED_EVENTS:
        assert f'"{event_type}"' in OPERATIONS_PATH.read_text(encoding="utf-8")
    assert "The two\nnames are not aliases" in _text()


def test_draft_local_boundary_and_same_conformance_matrix_are_explicit() -> None:
    text = _text()
    conformance = CONFORMANCE_PATH.read_text(encoding="utf-8")

    assert text.startswith("# Baseline Output v2 Normative Contract\n")
    assert "Status: **Draft public ABI; locally activated only" in text
    assert "trusted-host responsibilities" in text
    assert "passing the local matrix must not\nbe relabeled" in text
    assert "reference StateStore adapter" in text
    assert "independent stdlib adapter" in text
    assert "same provider-free, network-free,\nno-skip matrix" in text
    assert (
        _assignment(
            CONFORMANCE_PATH,
            "GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2",
        )
        == "pheroos-baseline-output-conformance-v2"
    )
    for label in (
        'label="quorum"',
        'label="direct"',
        'label="fallback"',
        'label="blocked"',
    ):
        assert label in conformance
    assert "legacy v1 bare `action_permission_issued` event" in text
