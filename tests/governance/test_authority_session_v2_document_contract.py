from __future__ import annotations

import ast
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs/protocol/authority-session-v2.md"
CONTRACTS_PATH = ROOT / "pheroos/governance/_authority_session_v2/contracts.py"
OPERATIONS_PATH = ROOT / "pheroos/governance/_authority_session_v2/operations.py"

REGISTRY_START = "<!-- authority-session-v2-registry:start -->"
REGISTRY_END = "<!-- authority-session-v2-registry:end -->"
OPERATIONS_START = "<!-- authority-session-v2-operations:start -->"
OPERATIONS_END = "<!-- authority-session-v2-operations:end -->"

EXPECTED_OPERATIONS = (
    ("VERIFY_SIGNAL", "verify_signal"),
    ("EVALUATE_QUORUM", "evaluate_quorum"),
    ("QUALIFY_EVIDENCE", "qualify_evidence"),
    ("RESOLVE_STOP", "resolve_stop"),
    ("ADVANCE_REPLAY", "advance_replay"),
    ("ISSUE_ACTION_PERMISSION", "issue_action_permission"),
    ("AUTHORIZE_OUTPUT", "authorize_output"),
    ("RETIRE_DOMAIN", "retire_domain"),
)

EXPECTED_IDENTIFIERS = {
    "authority_session": "pheroos-governance-authority-session-v2",
    "authority_session_conformance": (
        "pheroos-governance-authority-session-conformance-v2"
    ),
    "domain_retirement_request": ("pheroos-governance-domain-retirement-request-v2"),
    "issuer_capability": "pheroos-governance-issuer-capability-v2",
    "issuer_grant": "pheroos-governance-issuer-grant-v2",
    "issuer_grant_state": "pheroos-governance-issuer-grant-state-v2",
    "issuer_grant_verification": "pheroos-issuer-grant-verification-v2",
    "issuer_grant_verifier": "pheroos-issuer-grant-verifier-v2",
    "issuer_operation": "pheroos-governance-issuer-operation-v2",
    "verified_signal_request": "pheroos-governance-verified-signal-request-v2",
    "verified_signal_state": "pheroos-governance-verified-signal-state-v2",
    "verifier_conformance": "pheroos-issuer-grant-verifier-conformance-v2",
}

EXPECTED_GRANT_FIELDS = (
    "domain_root",
    "scope_ref",
    "issuer_ref",
    "grant_ref",
    "grant_binding_ref",
    "operations",
    "target_refs",
    "action_refs",
    "issued_epoch",
    "not_before_epoch",
    "expires_at_epoch",
    "revocation_generation",
    "schema",
    "canonical_version",
    "grant_root",
)

EXPECTED_VERIFICATION_FIELDS = (
    "grant_root",
    "grant_binding_ref",
    "verifier_ref",
    "accepted",
    "verified_epoch",
    "schema",
    "canonical_version",
    "verification_root",
)

EXPECTED_SIGNAL_FIELDS = (
    "domain_root",
    "scope_ref",
    "run_ref",
    "request_ref",
    "transition_id",
    "signal_ref",
    "target_ref",
    "signal_root",
    "evidence_root",
    "status",
    "observed_epoch",
    "stream_ref",
    "schema",
    "canonical_version",
    "request_root",
)

EXPECTED_RETIREMENT_FIELDS = (
    "domain_root",
    "scope_ref",
    "run_ref",
    "request_ref",
    "transition_id",
    "stream_refs",
    "reason_ref",
    "observed_epoch",
    "schema",
    "canonical_version",
    "request_root",
)

EXPECTED_SESSION_BINDINGS = (
    "domain_root",
    "scope_ref",
    "run_ref",
    "request_ref",
    "request_root",
    "operation",
    "observed_epoch",
    "grant_ref",
    "grant_root",
    "grant_binding_ref",
    "grant_expected_revision",
    "grant_expected_root",
    "lifecycle_expected_revision",
    "lifecycle_expected_root",
    "target_refs",
    "action_refs",
)

EXPECTED_EVENTS = (
    "issuer_grant_activated",
    "issuer_grant_revoked",
    "signal_verified",
    "domain_retired",
)


def _text() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _between(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1
    assert text.count(end) == 1
    return text.split(start, 1)[1].split(end, 1)[0]


def _code_lines(text: str, start: str, end: str) -> tuple[str, ...]:
    section = _between(text, start, end)
    match = re.fullmatch(r"\s*```text\s*\n(.*?)\n```\s*", section, re.DOTALL)
    assert match is not None
    return tuple(line for line in match.group(1).splitlines() if line)


def _json_registry() -> dict[str, Any]:
    section = _between(_text(), REGISTRY_START, REGISTRY_END)
    match = re.fullmatch(r"\s*```json\s*\n(.*?)\n```\s*", section, re.DOTALL)
    assert match is not None

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            assert key not in result
            result[key] = value
        return result

    payload = json.loads(match.group(1), object_pairs_hook=unique_object)
    assert isinstance(payload, dict)
    return payload


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_fields(path: Path, class_name: str) -> tuple[str, ...]:
    for node in _module(path).body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return tuple(
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            )
    raise AssertionError(f"missing class {class_name}")


def _function(path: Path, function_name: str) -> ast.FunctionDef:
    for node in _module(path).body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise AssertionError(f"missing function {function_name}")


def test_contract_is_public_draft_with_local_activation_and_pending_auth_gate() -> None:
    text = _text()

    assert text.startswith("# Authority Session v2 Normative Contract\n")
    assert (
        "Status: **Draft public ABI with provider-free Conformance; active local "
        "profile,\nauthenticated production promotion still gated**"
    ) in text
    assert "`pheroos.governance._authority_session_v2`" in text
    assert "`pheroos.governance.authority_session_v2`" in text
    assert "Public Draft\navailability now participates" in text
    assert "implementation not started" not in text
    assert "necessary evidence, not self-certification" in text


def test_registry_and_closed_operation_order_are_exact() -> None:
    registry = _json_registry()

    assert registry == {
        "format_version": 1,
        "status": "draft-active-local",
        "identifiers": EXPECTED_IDENTIFIERS,
        "operations": [
            {"label": label, "wire": wire} for label, wire in EXPECTED_OPERATIONS
        ],
        "stream_prefixes": {
            "issuer_grant": "authority:issuer-grant:",
            "verified_signal": "authority:verified-signal:",
        },
    }
    assert _code_lines(_text(), OPERATIONS_START, OPERATIONS_END) == tuple(
        f"{label}={wire}" for label, wire in EXPECTED_OPERATIONS
    )
    assert "Only `VERIFY_SIGNAL` and `RETIRE_DOMAIN` have request/session" in _text()
    assert "An empty tuple grants no implicit target or action." in _text()


def test_documented_portable_fields_match_the_implementation_owner() -> None:
    text = _text()
    expected = (
        (
            "GovernanceIssuerGrantV2",
            "authority-session-v2-grant-fields",
            EXPECTED_GRANT_FIELDS,
        ),
        (
            "IssuerGrantVerificationV2",
            "authority-session-v2-verification-fields",
            EXPECTED_VERIFICATION_FIELDS,
        ),
        (
            "GovernanceVerifiedSignalRequestV2",
            "authority-session-v2-signal-request-fields",
            EXPECTED_SIGNAL_FIELDS,
        ),
        (
            "GovernanceDomainRetirementRequestV2",
            "authority-session-v2-retirement-request-fields",
            EXPECTED_RETIREMENT_FIELDS,
        ),
    )

    for class_name, marker, fields in expected:
        documented = _code_lines(
            text,
            f"<!-- {marker}:start -->",
            f"<!-- {marker}:end -->",
        )
        assert documented == fields
        assert _class_fields(CONTRACTS_PATH, class_name) == fields


def test_grant_and_verification_semantics_do_not_invent_old_fields() -> None:
    text = _text()

    assert "`GovernanceIssuerGrantV2` is proposal/configuration data." in text
    assert "It is not a bearer\ncredential" in text
    assert "this class\ndoes not invent a binding-policy evaluator" in text
    assert "issued_epoch <= not_before_epoch <= expires_at_epoch" in text
    assert "not_before_epoch <= observed_epoch <= expires_at_epoch" in text
    assert "accepted is True" in text
    assert "There is no `verifier_version` property" in text
    assert "verified_epoch` equals the operation's `observed_epoch`" in text
    for obsolete in (
        "grant_id",
        "allowed_operations",
        "allowed_target_refs",
        "allowed_action_refs",
        "expires_after_epoch",
        "verification_policy_ref",
        "verification_expires_after_epoch",
        "verification_evidence_root",
    ):
        assert obsolete not in text


def test_transition_and_store_version_boundaries_are_explicit() -> None:
    text = _text()

    assert "MUST NOT equal the\nreserved StateStore value `genesis`" in text
    assert "`state_store_version` MUST equal" in text
    assert "Shape compatibility is not version\ncompatibility" in text
    assert "fail closed on a missing, mismatched, or drifting\nversion" in text
    assert "event lineage `domain_root`" in text
    assert "MUST equal the batch's exact `domain_root`" in text


def test_verifier_protocol_and_profile_behavior_are_exact() -> None:
    text = _text()
    source = CONTRACTS_PATH.read_text(encoding="utf-8")

    verifier_class = next(
        node
        for node in _module(CONTRACTS_PATH).body
        if isinstance(node, ast.ClassDef) and node.name == "IssuerGrantVerifierV2"
    )
    method = next(
        node
        for node in verifier_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "verify_issuer_grant_v2"
    )
    assert tuple(arg.arg for arg in method.args.args) == ("self", "grant")
    assert tuple(arg.arg for arg in method.args.kwonlyargs) == ("observed_epoch",)
    assert "def verifier_version" not in source
    assert "For `pheroos-scoped-authority-local-v2`, the verifier argument" in text
    assert "Supplying a verifier fails with\n`authority_profile_unsupported`." in text
    assert "a conforming host verifier is\nrequired" in text
    assert (
        "same transition retry may recover the committed result without calling" in text
    )


def test_stream_derivation_and_event_names_match_implementation() -> None:
    text = _text()

    assert "grant_payload = UTF8(scope_ref) || 0x00 || UTF8(grant_ref)" in text
    assert 'grant_stream_ref = "authority:issuer-grant:" ||' in text
    assert "signal_payload = UTF8(scope_ref) || 0x00 || UTF8(signal_ref)" in text
    assert 'stream_ref = "authority:verified-signal:" ||' in text
    assert "bare 64-hex suffix, not a `sha256:` suffix" in text
    assert (
        _code_lines(
            text,
            "<!-- authority-session-v2-events:start -->",
            "<!-- authority-session-v2-events:end -->",
        )
        == EXPECTED_EVENTS
    )
    operations_source = OPERATIONS_PATH.read_text(encoding="utf-8")
    for event in EXPECTED_EVENTS:
        assert f'"{event}"' in operations_source
        assert f"`{event}`" in text


def test_grant_lifecycle_is_atomic_and_terminal() -> None:
    text = _text()

    assert "grant stream's genesis head" in text
    assert "current `authority:domain-lifecycle` head" in text
    assert "Revocation writes from the exact active grant head" in text
    assert "generation plus\none" in text
    assert "reactivation of a used\ngrant stream are forbidden" in text
    assert "no operation may publish a\npartial state/Trace result" in text


def test_capability_and_session_handles_are_exactly_opaque() -> None:
    text = _text()

    assert "final, slotted, non-dataclass local object" in text
    assert "the exact selected `GovernanceStateStoreV2` writer object" in text
    assert "the exact selected `AuthorityDomainV2` object" in text
    assert "one exact `run_ref`" in text
    for snippet in (
        "GovernanceIssuerCapabilityV2(...) raises TypeError",
        "copy.copy(capability) is capability",
        "copy.deepcopy(capability) is capability",
        "pickle.dumps(capability) raises TypeError",
        'hasattr(capability, "to_dict") is False',
        'hasattr(capability, "from_dict") is False',
        "The session is also final, slotted, immutable, non-dataclass",
        "Copy and deepcopy return the identical object.",
    ):
        assert snippet in text
    assert (
        _code_lines(
            text,
            "<!-- authority-session-v2-session-bindings:start -->",
            "<!-- authority-session-v2-session-bindings:end -->",
        )
        == EXPECTED_SESSION_BINDINGS
    )
    assert "Empty grant bounds are not\nwildcards." in text


def test_operation_signatures_match_the_public_draft_surface() -> None:
    text = _text()
    block = _between(
        text,
        "<!-- authority-session-v2-entrypoints:start -->",
        "<!-- authority-session-v2-entrypoints:end -->",
    )

    expected = {
        "activate_governance_issuer_grant_v2": (
            ("store", "domain", "grant", "transition_id", "observed_epoch", "verifier"),
            (),
            1,
        ),
        "revoke_governance_issuer_grant_v2": (
            ("store", "domain", "grant_ref", "transition_id", "observed_epoch"),
            (),
            0,
        ),
        "bind_governance_issuer_capability_v2": (
            ("store", "domain", "grant", "run_ref", "observed_epoch", "verifier"),
            (),
            1,
        ),
        "open_governance_authority_session_v2": (
            ("capability", "request"),
            (),
            0,
        ),
        "commit_verified_signal_v2": (
            ("request",),
            ("authority_session",),
            0,
        ),
        "retire_governance_domain_v2": (
            ("request",),
            ("authority_session",),
            0,
        ),
    }
    for name, (positional, keyword_only, positional_defaults) in expected.items():
        node = _function(OPERATIONS_PATH, name)
        assert tuple(arg.arg for arg in node.args.args) == positional
        assert tuple(arg.arg for arg in node.args.kwonlyargs) == keyword_only
        assert len(node.args.defaults) == positional_defaults
        assert f"def {name}(" in block

    assert block.count("authority_session: object = None") == 2
    assert "state_store" not in block
    assert (
        "The two commit entrypoints deliberately have no `state_store`/writer" in text
    )
    assert "the complete\nportable request, not a loose list" in text


def test_session_authorization_uses_captured_atomic_preconditions() -> None:
    text = _text()
    section = text.split("## 9. Atomic session authorization read-set", 1)[1]
    section = section.split("## 10.", 1)[0]

    assert "active grant stream revision and head root" in section
    assert "`authority:domain-lifecycle` stream revision and head root" in section
    assert (
        "captured preconditions plus\nthe signal write stream's current head" in section
    )
    assert "The grant and lifecycle entries are unconditional." in section
    assert "same atomic boundary" in section
    assert "the captured atomic\npreconditions remain authoritative" in section


def test_verified_signal_request_and_commit_are_exactly_bound() -> None:
    text = _text()

    assert "`status` is exactly `verified` or `rejected`." in text
    assert "`VERIFY_SIGNAL` session" in text
    assert "is the issuance trust root for this slice" in _flat(text)
    assert "There is no additional signal-policy evaluator in this ABI." in text
    assert "`governance_action_not_authorized`" in text
    assert "`transition_id` is taken directly from the request during\ncommit" in text
    assert "commit_verified_signal_v2(\n    request," in text
    assert "session's private writer" in text
    assert "`pheroos-governance-verified-signal-state-v2`" in text
    assert "`signal_verified` Trace event" in text
    for obsolete in (
        "source_ref",
        "subject_ref",
        "provenance_ref",
        "signal_payload_root",
    ):
        assert obsolete not in text


def test_retirement_requires_caller_declared_complete_stream_set() -> None:
    text = _text()

    assert "`stream_refs` is an exact UTF-8-sorted, duplicate-free tuple" in text
    assert "complete current set of non-lifecycle streams" in text
    assert "include the session grant stream exactly once" in text
    assert "MUST NOT\ninclude `authority:domain-lifecycle`" in text
    assert "has no stream\nenumeration API" in text
    assert "does not discover or\nguess the domain's stream set" in text
    assert "omitted grant stream or included\nlifecycle stream" in text
    assert "`governance_read_set_invalid` at `/stream_refs`" in text
    assert "builds the existing\n`GovernanceDomainSealV2`" in text
    assert "`domain_retired` Trace event" in text
    assert "There is no check-then-seal gap." in text


def test_binding_exceptions_and_commit_attempts_are_distinct() -> None:
    text = _text()

    assert "`GovernanceAuthorityBindingErrorV2` is a `ValueError` subclass" in text
    assert "`AuthorityDiagnosticCodeV2 code`" in text
    assert "canonical JSON\nPointer `path`" in text
    assert "Its text is not a wire protocol and MUST NOT be parsed." in text
    assert "wrong request Python\ntype still raises `TypeError`" in text
    assert "missing, fake, or mismatched session" in text
    for diagnostic in (
        "authority_session_required",
        "authority_session_store_mismatch",
        "authority_scope_mismatch",
        "authority_operation_denied",
        "authority_binding_mismatch",
        "authority_grant_unverified",
        "authority_grant_expired",
        "authority_grant_revoked",
        "governance_action_not_authorized",
        "governance_read_set_invalid",
        "governance_read_set_stale",
        "governance_transition_conflict",
        "governance_domain_sealed",
        "governance_finality_unavailable",
        "governance_trace_lineage_invalid",
    ):
        assert diagnostic in text
    assert "AuthorityV2ProtocolError" not in text


def test_trace_restart_non_goals_and_activation_gate_are_explicit() -> None:
    text = _text()

    assert "A failed attempt\ndoes not publish durable state, a receipt" in text
    assert "MUST NOT include opaque handles" in text
    assert "Capability and session handles may\nnot" in text
    assert (
        "No pickle, object id, hidden portable nonce, process-global registry" in text
    )
    assert "generic capability/security/policy manager" in text
    assert (
        "Passing the bundled\nmatrix alone does not establish authenticated "
        "production compatibility"
    ) in text
    assert "pheroos.protocol.v2 + local profile -> active Draft exact dispatch" in text
    assert "authenticated production/Stable claim -> gated on external verifier" in text
    assert "legacy v1 behavior -> unchanged" in text
