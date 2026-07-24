from __future__ import annotations

import json
import pickle
from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance._risk_policy import RiskBand
from pheroos.governance._risk_v2 import (
    MAX_RISK_INPUT_ROOTS_V2,
    MAX_RISK_RATIONALE_CODES_V2,
    MAX_RISK_RESOURCE_DEPTH_V2,
    MAX_RISK_RESOURCE_NODES_V2,
    MAX_RISK_RESOURCE_TEXT_BYTES_V2,
    MAX_RISK_SNAPSHOT_BYTES_V2,
    MAX_RISK_SOURCE_TRACE_ROOTS_V2,
    MAX_RISK_TEXT_BYTES_V2,
    RISK_GENESIS_SNAPSHOT_ROOT_V2,
    RISK_GENESIS_TRANSITION_ID_V2,
    RiskAssessmentRecordV2,
    RiskStateAdvanceRequestV2,
    RiskStateSnapshotV2,
    RiskThresholdSnapshotV2,
    VerifiedRiskSourceV2,
    VerifiedRiskStateV2,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    prepare_risk_state_advance_v2,
    rehydrate_risk_state_v2,
    require_current_risk_state_v2,
    risk_state_is_current_v2,
    risk_state_stream_ref_v2,
    risk_state_transition_id_v2,
)
from pheroos.governance._risk_v2.resources import (
    _preflight_portable_resources_v2,
)
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.risk import (
    initialize_risk_assessment_chain,
    issue_commit_threshold_snapshot,
    issue_risk_assessment,
)
from pheroos.protocol.authority_manifest_v2 import (
    ScopedProtocolManifestV2,
    scoped_capability_manifest_v2_from_dict,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
)
from pheroos.protocol.commit_models import (
    CERTIFIED_COMMIT_PROFILE_VERSION,
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from tests.governance.test_commit_risk import (
    INPUT_A,
    INPUT_B,
    MANIFEST_ROOT,
    PROFILE,
    TARGET,
    policy,
)

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_REF = "scoped.output.review"
RUN_REF = "run:risk-v2"
EPOCH = 7


def test_risk_v2_owner_does_not_import_the_legacy_risk_owner() -> None:
    repository = Path(__file__).resolve().parents[2]
    owners = [
        *sorted((repository / "pheroos/governance/_risk_v2").glob("*.py")),
        repository / "pheroos/governance/risk_v2.py",
    ]
    forbidden = (
        "pheroos.governance._risk.",
        "from pheroos.governance.risk import",
    )
    for owner in owners:
        source = owner.read_text(encoding="utf-8")
        assert all(marker not in source for marker in forbidden), owner


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _manifest(
    commit_policy: CollectiveCommitPolicy | None = None,
) -> ScopedProtocolManifestV2:
    payload = json.loads(
        (ROOT / "examples/scoped-output-protocol/capability.json").read_text()
    )
    scoped = scoped_capability_manifest_v2_from_dict(payload).protocol
    selected_policy = policy() if commit_policy is None else commit_policy
    selected_policy = replace(
        selected_policy,
        terminal_outcome=replace(
            selected_policy.terminal_outcome,
            safe_fallback_candidate=scoped.quorum_policy.fallback_candidate,
        ),
    )
    return replace(
        scoped,
        collective_commit_policy=selected_policy,
    )


def _policy_with_low_extensions(
    extensions: dict[str, Any],
) -> CollectiveCommitPolicy:
    selected = policy()
    bands = dict(selected.risk_bands)
    bands[RiskBand.LOW.value] = replace(
        bands[RiskBand.LOW.value],
        extensions=extensions,
    )
    return replace(selected, risk_bands=bands)


@dataclass(frozen=True, slots=True)
class _Context:
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    capability: GovernanceIssuerCapabilityV2


def _context(
    *,
    scope_ref: str = "scope:risk-v2",
    run_ref: str = RUN_REF,
    target_ref: str = TARGET,
    store_wrapper: Callable[[GovernanceStateStoreV2, str], GovernanceStateStoreV2]
    | None = None,
) -> _Context:
    domain = AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )
    base: GovernanceStateStoreV2 = InMemoryGovernanceStateStoreV2((domain,))
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:risk-v2",
        grant_ref="grant:risk-v2",
        grant_binding_ref=_root(f"grant-binding:{scope_ref}"),
        operations=(GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,),
        target_refs=(target_ref,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=1_000,
        revocation_generation=0,
    )
    activated = activate_governance_issuer_grant_v2(
        base, domain, grant, f"transition:grant:{scope_ref}", 1
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    store = base if store_wrapper is None else store_wrapper(base, domain.domain_root)
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        run_ref,
        EPOCH,
    )
    return _Context(domain, store, grant, capability)


def _request(
    context: _Context,
    *,
    advance_ref: str,
    risk_band: RiskBand = RiskBand.LOW,
    parent: RiskStateSnapshotV2 | None = None,
    current_step: int = 2,
    issued_at_step: int | None = None,
    expires_at_step: int = 20,
    run_ref: str = RUN_REF,
    target_ref: str = TARGET,
    risk_input_roots: tuple[str, ...] = (INPUT_A,),
    rationale_codes: tuple[str, ...] = ("governance_risk_classification",),
    manifest: ScopedProtocolManifestV2 | None = None,
    profile: str = PROFILE,
    issuer_ref: str = "issuer:risk-v2",
    source_trace_roots: tuple[str, ...] | None = None,
    epoch: int = EPOCH,
) -> tuple[RiskStateAdvanceRequestV2, VerifiedRiskSourceV2]:
    selected_manifest = _manifest() if manifest is None else manifest
    return prepare_risk_state_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=selected_manifest,
        profile=profile,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=epoch,
        advance_ref=advance_ref,
        current_step=current_step,
        assessment_ref=f"assessment:{advance_ref}",
        risk_band=risk_band,
        risk_input_roots=risk_input_roots,
        rationale_codes=rationale_codes,
        assessment_method="declared-risk-matrix-v1",
        issuer_ref=issuer_ref,
        issued_at_step=current_step if issued_at_step is None else issued_at_step,
        expires_at_step=expires_at_step,
        provenance_ref=f"urn:test:{advance_ref}",
        source_trace_roots=(
            (_root(f"trace:{advance_ref}"),)
            if source_trace_roots is None
            else source_trace_roots
        ),
        parent_snapshot=parent,
    )


def _advance(
    context: _Context,
    request: RiskStateAdvanceRequestV2,
    source: VerifiedRiskSourceV2,
) -> tuple[GovernanceCommitAttemptV2, object]:
    session = open_risk_authority_session_v2(context.capability, request)
    return (
        advance_risk_state_v2(
            request,
            source=source,
            authority_session=session,
        ),
        session,
    )


def test_portable_contracts_bind_full_stream_context_and_reject_tamper() -> None:
    context = _context(scope_ref="scope:risk-v2:portable")
    request, source = _request(context, advance_ref="advance:portable")
    snapshot = request.snapshot
    expected = risk_state_stream_ref_v2(
        context.domain.scope_ref,
        PROFILE,
        CommitAssurance.EVIDENCE_BOUND,
        snapshot.manifest_root,
        snapshot.commit_policy_root,
        snapshot.risk_policy_root,
        PROTOCOL_REF,
        RUN_REF,
        TARGET,
    )
    assert request.stream_ref == expected
    assert RiskStateAdvanceRequestV2.from_dict(request.to_dict()) == request
    assert json.loads(request.canonical_bytes()) == request.to_dict()
    assert source.context_root == snapshot.source_context_root
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(source)

    body = request.to_dict()
    body["run_ref"] = "run:cross-context"
    with pytest.raises(ValueError, match="cross-bound"):
        RiskStateAdvanceRequestV2.from_dict(body)
    snapshot_body = snapshot.to_dict()
    snapshot_body["snapshot_root"] = _root("forged-snapshot")
    with pytest.raises(ValueError, match="snapshot_root"):
        RiskStateSnapshotV2.from_dict(snapshot_body)


def test_risk_wire_decode_rejects_empty_roots_and_silent_array_normalization() -> None:
    context = _context(scope_ref="scope:risk-v2:canonical-wire")
    request, _ = _request(
        context,
        advance_ref="advance:canonical-wire",
        risk_input_roots=(INPUT_A, INPUT_B),
        rationale_codes=("alpha", "omega"),
        source_trace_roots=(_root("trace:alpha"), _root("trace:omega")),
    )

    missing_request_root = request.to_dict()
    missing_request_root["request_root"] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        RiskStateAdvanceRequestV2.from_dict(missing_request_root)

    missing_nested_roots = request.to_dict()
    snapshot = cast(dict[str, Any], missing_nested_roots["snapshot"])
    assessment = cast(dict[str, Any], snapshot["assessment"])
    threshold = cast(dict[str, Any], snapshot["threshold"])
    for owner, field in (
        (missing_nested_roots, "request_root"),
        (snapshot, "snapshot_root"),
        (assessment, "assessment_root"),
        (threshold, "threshold_root"),
    ):
        owner[field] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        RiskStateAdvanceRequestV2.from_dict(missing_nested_roots)

    reordered = request.to_dict()
    reordered_snapshot = cast(dict[str, Any], reordered["snapshot"])
    reordered_assessment = cast(dict[str, Any], reordered_snapshot["assessment"])
    for field in ("risk_input_roots", "rationale_codes", "source_trace_roots"):
        reordered_assessment[field] = list(
            reversed(cast(list[object], reordered_assessment[field]))
        )
    with pytest.raises(ValueError, match="not canonical wire"):
        RiskStateAdvanceRequestV2.from_dict(reordered)


def test_risk_request_rejects_bool_epoch_even_when_snapshot_epoch_is_one() -> None:
    context = _context(scope_ref="scope:risk-v2:bool-epoch")
    request, _ = _request(
        context,
        advance_ref="advance:bool-epoch",
        epoch=1,
    )

    with pytest.raises(ValueError, match="request epoch"):
        replace(request, epoch=True, request_root="")


def test_prepare_derives_exact_manifest_policy_binding_and_rejects_cross_source() -> (
    None
):
    context = _context(scope_ref="scope:risk-v2:manifest-binding")
    manifest = _manifest()
    request, source = _request(
        context,
        advance_ref="advance:manifest-binding",
        manifest=manifest,
    )
    snapshot = request.snapshot
    assert snapshot.manifest_root == manifest.manifest_root
    assert snapshot.commit_policy_root == commit_policy_fingerprint(
        cast(CollectiveCommitPolicy, manifest.collective_commit_policy),
        profile=PROFILE,
    )
    assert snapshot.protocol_ref == manifest.id
    assert snapshot.target_ref == TARGET
    assert snapshot.assurance is CommitAssurance.EVIDENCE_BOUND

    with pytest.raises(TypeError, match="exact scoped manifest"):
        _request(
            context,
            advance_ref="advance:manifest-not-exact",
            manifest=cast(Any, manifest.to_dict()),
        )
    with pytest.raises(ValueError, match="target is not declared"):
        _request(
            context,
            advance_ref="advance:manifest-target",
            manifest=manifest,
            target_ref="decision:not-declared",
        )
    with pytest.raises(RuntimeError, match="profile/assurance mismatch"):
        _request(
            context,
            advance_ref="advance:manifest-profile",
            manifest=manifest,
            profile=CERTIFIED_COMMIT_PROFILE_VERSION,
        )

    other_manifest = replace(
        manifest,
        extensions={"x-risk-v2-manifest": {"revision": 2}},
    )
    other_request, other_source = _request(
        context,
        advance_ref="advance:manifest-binding",
        manifest=other_manifest,
    )
    assert other_request.snapshot.manifest_root != snapshot.manifest_root
    assert other_request.snapshot.commit_policy_root == snapshot.commit_policy_root
    assert other_request.snapshot.risk_policy_root == snapshot.risk_policy_root
    assert other_request.snapshot.threshold == snapshot.threshold
    assert other_request.stream_ref != request.stream_ref

    cross = advance_risk_state_v2(
        request,
        source=other_source,
        authority_session=open_risk_authority_session_v2(context.capability, request),
    )
    assert cross.disposition is GovernanceCommitDispositionV2.INVALID

    object.__setattr__(source, "_manifest", other_manifest)
    tampered = advance_risk_state_v2(
        request,
        source=source,
        authority_session=open_risk_authority_session_v2(context.capability, request),
    )
    assert tampered.disposition is GovernanceCommitDispositionV2.INVALID


def test_manifest_authority_selector_and_assessment_issuer_bind_session() -> None:
    profile_context = _context(scope_ref="scope:risk-v2:authority-profile")
    manifest = _manifest()
    mismatched_manifest = replace(
        manifest,
        authority_policy=replace(
            manifest.authority_policy,
            profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
        ),
    )
    profile_request, profile_source = _request(
        profile_context,
        advance_ref="advance:authority-profile",
        manifest=mismatched_manifest,
    )
    profile_session = open_risk_authority_session_v2(
        profile_context.capability,
        profile_request,
    )
    rejected_profile = advance_risk_state_v2(
        profile_request,
        source=profile_source,
        authority_session=profile_session,
    )
    assert rejected_profile.disposition is GovernanceCommitDispositionV2.INVALID
    assert rejected_profile.failure is not None
    assert rejected_profile.failure.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED
    )
    assert rejected_profile.failure.path == "/manifest/authority_policy"
    assert (
        profile_context.store.load_head_v2(
            profile_request.scope_ref,
            profile_request.stream_ref,
        ).revision
        == 0
    )

    issuer_context = _context(scope_ref="scope:risk-v2:issuer-binding")
    spoofed, spoofed_source = _request(
        issuer_context,
        advance_ref="advance:issuer-binding",
        issuer_ref="issuer:spoofed-victim",
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as issuer_caught:
        open_risk_authority_session_v2(issuer_context.capability, spoofed)
    assert issuer_caught.value.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    assert issuer_caught.value.path == "/snapshot/assessment/issuer_ref"

    genuine, _ = _request(
        issuer_context,
        advance_ref="advance:issuer-binding",
    )
    rejected_issuer = advance_risk_state_v2(
        spoofed,
        source=spoofed_source,
        authority_session=open_risk_authority_session_v2(
            issuer_context.capability,
            genuine,
        ),
    )
    assert rejected_issuer.disposition is GovernanceCommitDispositionV2.INVALID
    assert (
        issuer_context.store.load_head_v2(
            spoofed.scope_ref,
            spoofed.stream_ref,
        ).revision
        == 0
    )


def test_source_reconstruction_has_no_authority_sentinel() -> None:
    context = _context(scope_ref="scope:risk-v2:source-reconstruction")
    request, source = _request(
        context,
        advance_ref="advance:source-reconstruction",
    )
    session = open_risk_authority_session_v2(context.capability, request)

    incomplete = object.__new__(VerifiedRiskSourceV2)
    object.__setattr__(
        incomplete,
        "_request",
        RiskStateAdvanceRequestV2.from_dict(request.to_dict()),
    )
    rejected_incomplete = advance_risk_state_v2(
        request,
        source=incomplete,
        authority_session=session,
    )
    assert rejected_incomplete.disposition is GovernanceCommitDispositionV2.INVALID

    original_binding = object.__getattribute__(source, "_binding")
    original_manifest = object.__getattribute__(source, "_manifest")
    reconstructed = object.__new__(VerifiedRiskSourceV2)
    object.__setattr__(
        reconstructed,
        "_request",
        RiskStateAdvanceRequestV2.from_dict(request.to_dict()),
    )
    object.__setattr__(reconstructed, "_binding", replace(original_binding))
    object.__setattr__(
        reconstructed,
        "_manifest",
        ScopedProtocolManifestV2.from_dict(original_manifest.to_dict()),
    )
    assert reconstructed.context_root == source.context_root

    no_session = advance_risk_state_v2(
        request,
        source=reconstructed,
        authority_session=None,
    )
    assert no_session.disposition is not GovernanceCommitDispositionV2.COMMITTED
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision
        == 0
    )

    accepted = advance_risk_state_v2(
        request,
        source=reconstructed,
        authority_session=session,
    )
    assert accepted.disposition is GovernanceCommitDispositionV2.COMMITTED


def test_run_scope_remains_explicit_source_and_session_bound() -> None:
    context = _context(scope_ref="scope:risk-v2:run-binding")
    first, _ = _request(
        context,
        advance_ref="advance:run-binding",
        run_ref=RUN_REF,
    )
    second, second_source = _request(
        context,
        advance_ref="advance:run-binding",
        run_ref="run:risk-v2:other",
    )
    assert first.snapshot.manifest_root == second.snapshot.manifest_root
    assert first.stream_ref != second.stream_ref
    rejected = advance_risk_state_v2(
        first,
        source=second_source,
        authority_session=open_risk_authority_session_v2(context.capability, first),
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID


def test_source_trace_roots_are_canonical_bounded_and_utf8_safe() -> None:
    context = _context(scope_ref="scope:risk-v2:trace-roots")
    first = _root("source-trace:first")
    second = _root("source-trace:second")
    request, _ = _request(
        context,
        advance_ref="advance:trace-order",
        source_trace_roots=(second, first),
    )
    assessment = request.snapshot.assessment
    assert assessment.source_trace_roots == tuple(
        sorted((first, second), key=lambda item: item.encode("utf-8"))
    )
    assert RiskAssessmentRecordV2.from_dict(assessment.to_dict()) == assessment

    exact = tuple(
        _root(f"source-trace:{index}")
        for index in range(MAX_RISK_SOURCE_TRACE_ROOTS_V2)
    )
    exact_request, _ = _request(
        context,
        advance_ref="advance:trace-exact",
        source_trace_roots=exact,
    )
    assert len(exact_request.snapshot.assessment.source_trace_roots) == (
        MAX_RISK_SOURCE_TRACE_ROOTS_V2
    )
    with pytest.raises(ValueError, match="source trace roots count"):
        _request(
            context,
            advance_ref="advance:trace-empty",
            source_trace_roots=(),
        )
    with pytest.raises(ValueError, match="source trace roots contains a duplicate"):
        _request(
            context,
            advance_ref="advance:trace-duplicate",
            source_trace_roots=(first, first),
        )
    with pytest.raises(ValueError, match="source trace roots count"):
        _request(
            context,
            advance_ref="advance:trace-plus-one",
            source_trace_roots=(*exact, _root("source-trace:plus-one")),
        )

    invalid_utf8 = assessment.to_dict()
    invalid_utf8["source_trace_roots"] = ["\ud800"]
    with pytest.raises(ValueError, match="valid UTF-8"):
        RiskAssessmentRecordV2.from_dict(invalid_utf8)


def test_threshold_extensions_are_canonical_immutable_and_tamper_evident() -> None:
    context = _context(scope_ref="scope:risk-v2:threshold-extensions")
    base_request, _ = _request(
        context,
        advance_ref="advance:threshold-extensions",
    )
    extensions_a = {
        "x-risk-v2": {"weights": [1, 2], "mode": "strict"},
        "ext.vendor": {"enabled": True},
    }
    extensions_b = {
        "ext.vendor": {"enabled": True},
        "x-risk-v2": {"mode": "strict", "weights": [1, 2]},
    }
    request_a, _ = _request(
        context,
        advance_ref="advance:threshold-extensions",
        manifest=_manifest(_policy_with_low_extensions(extensions_a)),
    )
    request_b, _ = _request(
        context,
        advance_ref="advance:threshold-extensions",
        manifest=_manifest(_policy_with_low_extensions(extensions_b)),
    )
    threshold = request_a.snapshot.threshold
    assert threshold.threshold_root != base_request.snapshot.threshold.threshold_root
    assert threshold.threshold_root == request_b.snapshot.threshold.threshold_root
    assert threshold.to_dict()["extensions"] == extensions_a
    assert RiskThresholdSnapshotV2.from_dict(threshold.to_dict()) == threshold
    with pytest.raises(TypeError):
        threshold.extensions["x-risk-v2"] = {}  # type: ignore[index]

    tampered = threshold.to_dict()
    tampered_extensions = cast(dict[str, Any], tampered["extensions"])
    cast(dict[str, Any], tampered_extensions["x-risk-v2"])["mode"] = "loose"
    with pytest.raises(ValueError, match="threshold_root"):
        RiskThresholdSnapshotV2.from_dict(tampered)

    invalid_extensions: tuple[tuple[object, type[Exception], str], ...] = (
        ({"not-namespaced": 1}, ValueError, "namespaced"),
        ({"x-risk-v2": 1.5}, TypeError, "floating-point"),
        ({1: "invalid-key"}, TypeError, "keys must be exact text"),
        ({"x-risk-v2": "\ud800"}, ValueError, "valid UTF-8"),
    )
    for value, error, match in invalid_extensions:
        with pytest.raises(error, match=match):
            replace(
                threshold,
                extensions=cast(Any, value),
                threshold_root="",
            )


def test_prepare_enforces_monotonic_band_frozen_expiry_and_window_reset() -> None:
    context = _context(scope_ref="scope:risk-v2:monotonic")
    low, _ = _request(context, advance_ref="advance:low")
    high, _ = _request(
        context,
        advance_ref="advance:high",
        risk_band=RiskBand.HIGH,
        parent=low.snapshot,
        current_step=3,
        risk_input_roots=(INPUT_A, INPUT_B),
    )
    same, _ = _request(
        context,
        advance_ref="advance:same",
        risk_band=RiskBand.HIGH,
        parent=high.snapshot,
        current_step=4,
    )
    assert high.snapshot.assessment.previous_assessment_root == (
        low.snapshot.assessment.assessment_root
    )
    assert high.snapshot.assessment.window_reset_required is True
    assert same.snapshot.assessment.window_reset_required is False
    with pytest.raises(ValueError, match="cannot decrease"):
        _request(
            context,
            advance_ref="advance:downgrade",
            risk_band=RiskBand.MODERATE,
            parent=high.snapshot,
            current_step=4,
        )
    with pytest.raises(ValueError, match="frozen expiry"):
        _request(
            context,
            advance_ref="advance:expiry",
            risk_band=RiskBand.CRITICAL,
            parent=high.snapshot,
            current_step=4,
            expires_at_step=21,
        )
    with pytest.raises(ValueError, match="advance issued_at_step"):
        _request(
            context,
            advance_ref="advance:step",
            risk_band=RiskBand.HIGH,
            parent=high.snapshot,
            current_step=4,
            issued_at_step=3,
        )


def test_fixed_lineage_allows_epoch_advance_and_resets_epoch_local_rules() -> None:
    context = _context(scope_ref="scope:risk-v2:epoch-advance")
    initial, _ = _request(
        context,
        advance_ref="advance:epoch-1",
        risk_band=RiskBand.HIGH,
        epoch=1,
        current_step=2,
        expires_at_step=20,
    )
    next_epoch, _ = _request(
        context,
        advance_ref="advance:epoch-7",
        risk_band=RiskBand.LOW,
        parent=initial.snapshot,
        epoch=7,
        current_step=8,
        expires_at_step=40,
    )

    assert next_epoch.stream_ref == initial.stream_ref
    assert next_epoch.snapshot.parent_epoch == 1
    assert next_epoch.snapshot.epoch == 7
    assert next_epoch.snapshot.assessment.window_reset_required is True
    assert next_epoch.snapshot.assessment.expires_at_step == 40

    same_epoch, _ = _request(
        context,
        advance_ref="advance:epoch-7-same",
        risk_band=RiskBand.LOW,
        parent=next_epoch.snapshot,
        epoch=7,
        current_step=9,
        expires_at_step=40,
    )
    assert same_epoch.snapshot.assessment.window_reset_required is False

    with pytest.raises(ValueError, match="epoch cannot move backwards"):
        _request(
            context,
            advance_ref="advance:epoch-regression",
            risk_band=RiskBand.CRITICAL,
            parent=next_epoch.snapshot,
            epoch=6,
            current_step=9,
            expires_at_step=50,
        )


def test_fixed_lineage_survives_more_than_store_final_head_epoch_bound() -> None:
    context = _context(scope_ref="scope:risk-v2:many-epochs")
    initial, initial_source = _request(
        context,
        advance_ref=f"advance:epoch:{EPOCH}",
        epoch=EPOCH,
        current_step=EPOCH + 1,
        expires_at_step=EPOCH + 11,
    )
    assert _advance(context, initial, initial_source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    stream_refs = {initial.stream_ref}
    final_request: RiskStateAdvanceRequestV2 | None = None
    final_source: VerifiedRiskSourceV2 | None = None

    # Prepare more epoch identities than a seal can carry final heads. Every
    # identity still resolves to the one fixed lineage; the final jump is then
    # committed against the real Store head to prove this is operational, not
    # merely a hash-level claim.
    for epoch in range(EPOCH + 1, EPOCH + 131):
        current_step = epoch + 1
        request, source = _request(
            context,
            advance_ref=f"advance:epoch:{epoch}",
            parent=initial.snapshot,
            epoch=epoch,
            current_step=current_step,
            expires_at_step=current_step + 10,
        )
        stream_refs.add(request.stream_ref)
        assert request.snapshot.parent_epoch == EPOCH
        final_request, final_source = request, source

    assert len(stream_refs) == 1
    assert final_request is not None and final_source is not None
    assert final_request.epoch == EPOCH + 130
    assert _advance(context, final_request, final_source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    assert (
        context.store.load_head_v2(
            context.domain.scope_ref, initial.stream_ref
        ).revision
        == 2
    )


def test_resource_preflight_and_declared_collection_bounds_are_exact() -> None:
    context = _context(scope_ref="scope:risk-v2:resources")
    roots = tuple(_root(f"input:{index}") for index in range(MAX_RISK_INPUT_ROOTS_V2))
    rationales = tuple(
        f"rationale:{index}" for index in range(MAX_RISK_RATIONALE_CODES_V2)
    )
    request, _ = _request(
        context,
        advance_ref="advance:resource-exact",
        risk_input_roots=roots,
        rationale_codes=rationales,
    )
    assert len(request.snapshot.assessment.risk_input_roots) == MAX_RISK_INPUT_ROOTS_V2
    assert len(request.snapshot.assessment.rationale_codes) == (
        MAX_RISK_RATIONALE_CODES_V2
    )
    with pytest.raises(ValueError, match="input roots count"):
        _request(
            context,
            advance_ref="advance:resource-input-plus-one",
            risk_input_roots=(*roots, _root("input:plus-one")),
        )
    with pytest.raises(ValueError, match="rationale codes count"):
        _request(
            context,
            advance_ref="advance:resource-rationale-plus-one",
            rationale_codes=(*rationales, "rationale:plus-one"),
        )
    RiskAssessmentRecordV2(
        assessment_ref="a" * MAX_RISK_TEXT_BYTES_V2,
        issuer_ref="issuer:risk",
        risk_band=RiskBand.LOW,
        risk_input_roots=(INPUT_A,),
        rationale_codes=("risk",),
        assessment_method="method",
        issued_at_step=1,
        expires_at_step=2,
        previous_assessment_root="",
        window_reset_required=False,
        provenance_ref="urn:risk",
        source_trace_roots=(_root("trace:risk"),),
    )
    with pytest.raises(ValueError, match="text bound"):
        replace(
            request.snapshot.assessment,
            assessment_ref="a" * (MAX_RISK_TEXT_BYTES_V2 + 1),
            assessment_root="",
        )

    exact_depth: object = "leaf"
    for _ in range(MAX_RISK_RESOURCE_DEPTH_V2):
        exact_depth = [exact_depth]
    _preflight_portable_resources_v2(exact_depth)
    with pytest.raises(ValueError, match="depth bound"):
        _preflight_portable_resources_v2([exact_depth])
    _preflight_portable_resources_v2([None] * (MAX_RISK_RESOURCE_NODES_V2 - 1))
    with pytest.raises(ValueError, match="node bound"):
        _preflight_portable_resources_v2([None] * MAX_RISK_RESOURCE_NODES_V2)
    _preflight_portable_resources_v2("a" * MAX_RISK_RESOURCE_TEXT_BYTES_V2)
    with pytest.raises(ValueError, match="aggregate text"):
        _preflight_portable_resources_v2("a" * (MAX_RISK_RESOURCE_TEXT_BYTES_V2 + 1))
    assert len(request.snapshot.canonical_bytes()) < MAX_RISK_SNAPSHOT_BYTES_V2

    def saturated_labels(prefix: str) -> tuple[str, ...]:
        result = []
        for index in range(MAX_RISK_RATIONALE_CODES_V2):
            lead = f"{prefix}:{index}:"
            result.append(lead + "x" * (MAX_RISK_TEXT_BYTES_V2 - len(lead)))
        return tuple(result)

    saturated_assessment = RiskAssessmentRecordV2(
        assessment_ref="assessment:snapshot-cap",
        issuer_ref="issuer:risk",
        risk_band=RiskBand.LOW,
        risk_input_roots=(INPUT_A,),
        rationale_codes=saturated_labels("rationale"),
        assessment_method="method",
        issued_at_step=1,
        expires_at_step=2,
        previous_assessment_root="",
        window_reset_required=False,
        provenance_ref="urn:risk",
        source_trace_roots=(_root("trace:risk"),),
    )
    saturated_threshold = RiskThresholdSnapshotV2(
        assessment_root=saturated_assessment.assessment_root,
        risk_policy_root=_root("snapshot-cap:risk-policy"),
        risk_band=RiskBand.LOW,
        minimum_positive_evidence=1,
        maximum_counterevidence=0,
        maximum_counterevidence_ratio_ppm=0,
        minimum_support_clusters=1,
        minimum_support_ratio_ppm=1,
        minimum_source_diversity=1,
        minimum_margin=1,
        stability_steps=1,
        required_challenge_categories=saturated_labels("challenge"),
        minimum_assurance=CommitAssurance.EVIDENCE_BOUND,
        publishable_outcomes=saturated_labels("publish"),
        executable_outcomes=saturated_labels("execute"),
        extensions={},
    )
    commit_root = _root("snapshot-cap:commit-policy")
    saturated_stream = risk_state_stream_ref_v2(
        context.domain.scope_ref,
        PROFILE,
        CommitAssurance.EVIDENCE_BOUND,
        MANIFEST_ROOT,
        commit_root,
        saturated_threshold.risk_policy_root,
        PROTOCOL_REF,
        RUN_REF,
        TARGET,
    )
    with pytest.raises(ValueError, match="snapshot exceeds"):
        RiskStateSnapshotV2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            manifest_root=MANIFEST_ROOT,
            commit_policy_root=commit_root,
            risk_policy_root=saturated_threshold.risk_policy_root,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            protocol_ref=PROTOCOL_REF,
            run_ref=RUN_REF,
            target_ref=TARGET,
            epoch=EPOCH,
            stream_ref=saturated_stream,
            transition_id=risk_state_transition_id_v2(
                saturated_stream, "advance:snapshot-cap"
            ),
            advance_ref="advance:snapshot-cap",
            revision=1,
            current_step=1,
            parent_revision=0,
            parent_epoch=None,
            parent_transition_id=RISK_GENESIS_TRANSITION_ID_V2,
            parent_snapshot_root=RISK_GENESIS_SNAPSHOT_ROOT_V2,
            assessment=saturated_assessment,
            threshold=saturated_threshold,
            source_context_root=_root("snapshot-cap:source"),
        )


def test_genesis_commits_exact_read_set_two_events_and_restart_wrapper() -> None:
    context = _context(scope_ref="scope:risk-v2:genesis")
    request, source = _request(context, advance_ref="advance:genesis")
    session = open_risk_authority_session_v2(context.capability, request)
    invalid = advance_risk_state_v2(
        request,
        source=request.to_dict(),
        authority_session=session,
    )
    assert invalid.disposition is GovernanceCommitDispositionV2.INVALID
    attempt = advance_risk_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert attempt.committed_transition is not None
    batch = attempt.committed_transition.batch
    assert {item.stream_ref for item in batch.read_set.entries} == {
        request.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    assert tuple(event.event_type for event in batch.trace_batch.events) == (
        "risk_state_advanced",
        "risk_assessed_v2",
    )
    assert all(
        event.lineage["read_set_root"] == batch.read_set.root()
        for event in batch.trace_batch.events
    )
    assert batch.trace_batch.events[1].lineage["risk_band"] == "LOW"

    restarted = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        cast(InMemoryGovernanceStateStoreV2, context.store).snapshot_v2()
    )
    verified = rehydrate_risk_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=restarted,
    )
    assert type(verified) is VerifiedRiskStateV2
    assert verified.position is GovernanceCommitPositionV2.CURRENT
    assert risk_state_is_current_v2(verified)
    assert require_current_risk_state_v2(verified) == request.snapshot
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(verified)


def test_child_stale_fork_exact_retry_after_revocation_and_conflict() -> None:
    context = _context(scope_ref="scope:risk-v2:linearity")
    genesis, genesis_source = _request(context, advance_ref="advance:genesis")
    accepted, _ = _advance(context, genesis, genesis_source)
    assert accepted.disposition is GovernanceCommitDispositionV2.COMMITTED
    child, child_source = _request(
        context,
        advance_ref="advance:child",
        risk_band=RiskBand.HIGH,
        parent=genesis.snapshot,
        current_step=3,
    )
    fork, fork_source = _request(
        context,
        advance_ref="advance:fork",
        risk_band=RiskBand.MODERATE,
        parent=genesis.snapshot,
        current_step=3,
    )
    committed, child_session = _advance(context, child, child_source)
    stale, _ = _advance(context, fork, fork_source)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert stale.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert stale.failure is not None
    assert stale.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE

    old = rehydrate_risk_state_v2(
        genesis.to_dict(), domain=context.domain, state_reader=context.store
    )
    assert old.position is GovernanceCommitPositionV2.SUPERSEDED
    assert not risk_state_is_current_v2(old)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        require_current_risk_state_v2(old)
    assert caught.value.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:risk:revoke",
        EPOCH + 1,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    retry = advance_risk_state_v2(
        child,
        source=None,
        authority_session=child_session,
    )
    assert retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert retry.committed_transition is not None
    assert committed.committed_transition is not None
    assert retry.committed_transition.receipt.receipt_root == (
        committed.committed_transition.receipt.receipt_root
    )

    conflict_context = _context(scope_ref="scope:risk-v2:conflict")
    first, first_source = _request(
        conflict_context, advance_ref="advance:same", risk_band=RiskBand.LOW
    )
    second, second_source = _request(
        conflict_context, advance_ref="advance:same", risk_band=RiskBand.HIGH
    )
    assert _advance(conflict_context, first, first_source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    conflict = _advance(conflict_context, second, second_source)[0]
    assert conflict.disposition is GovernanceCommitDispositionV2.INVALID
    assert conflict.failure is not None
    assert conflict.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT
    )


class _ObservingStore:
    def __init__(self, store: GovernanceStateStoreV2, domain_root: str) -> None:
        self.store = store
        self.domain_root = domain_root
        self.finality_transition_ids: set[str] = set()
        self.view_mutator: Callable[[GovernanceCommitViewV2], None] | None = None

    @property
    def state_store_version(self) -> str:
        return self.store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str):  # type: ignore[no-untyped-def]
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        if transition_id in self.finality_transition_ids:
            return GovernanceCommitViewV2(
                domain_root=self.domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
                expected_receipt_root=expected_receipt_root,
                disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
                failure=GovernanceFailureV2(
                    code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
                    path="/transition_id",
                    stage=GovernanceFailureStageV2.FINALITY,
                ),
                committed_transition=None,
                position_observation=None,
                observed_revision=None,
                observed_head_root=None,
            )
        view = self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if self.view_mutator is not None:
            self.view_mutator(view)
        return view

    def atomic_commit_v2(self, batch: Any) -> GovernanceCommitAttemptV2:
        return self.store.atomic_commit_v2(batch)


@pytest.mark.parametrize(
    "mutation",
    (
        "inclusion_delete",
        "inclusion_replace",
        "batch_delete",
        "position_delete",
    ),
)
def test_commit_view_canonicalization_rejects_missing_nested_artifacts(
    mutation: str,
) -> None:
    wrapper: _ObservingStore | None = None

    def wrap(store: GovernanceStateStoreV2, domain_root: str) -> GovernanceStateStoreV2:
        nonlocal wrapper
        wrapper = _ObservingStore(store, domain_root)
        return cast(GovernanceStateStoreV2, wrapper)

    context = _context(
        scope_ref=f"scope:risk-v2:canonical-view:{mutation}",
        store_wrapper=wrap,
    )
    assert wrapper is not None
    request, source = _request(
        context,
        advance_ref=f"advance:canonical-view:{mutation}",
    )
    committed, session = _advance(context, request, source)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED

    def mutate(view: GovernanceCommitViewV2) -> None:
        assert view.committed_transition is not None
        if mutation == "inclusion_delete":
            object.__setattr__(view.committed_transition, "inclusion_proof", None)
        elif mutation == "inclusion_replace":
            replacement = replace(
                view.committed_transition.inclusion_proof,
                transition_id="transition:foreign-inclusion",
                inclusion_root="",
            )
            object.__setattr__(
                view.committed_transition,
                "inclusion_proof",
                replacement,
            )
        elif mutation == "batch_delete":
            object.__setattr__(view.committed_transition, "batch", None)
        else:
            object.__setattr__(view, "position_observation", None)

    wrapper.view_mutator = mutate
    retry = advance_risk_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    assert retry.disposition is GovernanceCommitDispositionV2.INVALID
    assert retry.failure is not None
    assert retry.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        rehydrate_risk_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision
        == 1
    )


def test_forged_current_position_cannot_revive_superseded_risk_state() -> None:
    wrapper: _ObservingStore | None = None

    def wrap(store: GovernanceStateStoreV2, domain_root: str) -> GovernanceStateStoreV2:
        nonlocal wrapper
        wrapper = _ObservingStore(store, domain_root)
        return cast(GovernanceStateStoreV2, wrapper)

    context = _context(
        scope_ref="scope:risk-v2:forged-current-position",
        store_wrapper=wrap,
    )
    assert wrapper is not None
    parent, parent_source = _request(context, advance_ref="advance:parent")
    assert _advance(context, parent, parent_source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    verified_parent = rehydrate_risk_state_v2(
        parent.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    child, child_source = _request(
        context,
        advance_ref="advance:child",
        risk_band=RiskBand.HIGH,
        parent=parent.snapshot,
        current_step=3,
    )
    assert _advance(context, child, child_source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )

    def forge_current(view: GovernanceCommitViewV2) -> None:
        if view.transition_id != parent.transition_id:
            return
        assert view.position_observation is not None
        object.__setattr__(
            view.position_observation,
            "position",
            GovernanceCommitPositionV2.CURRENT,
        )

    wrapper.view_mutator = forge_current
    assert not risk_state_is_current_v2(verified_parent)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        require_current_risk_state_v2(verified_parent)
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    assert (
        context.store.load_head_v2(
            child.scope_ref,
            child.stream_ref,
        ).revision
        == 2
    )


def test_cross_context_read_set_and_finality_tamper_fail_closed() -> None:
    context = _context(scope_ref="scope:risk-v2:tamper")
    request, source = _request(context, advance_ref="advance:tamper")
    wrong, wrong_source = _request(
        context, advance_ref="advance:wrong-source", risk_band=RiskBand.HIGH
    )
    wrong_session = open_risk_authority_session_v2(context.capability, request)
    rejected = advance_risk_state_v2(
        request,
        source=wrong_source,
        authority_session=wrong_session,
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    assert _advance(context, request, source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    del wrong

    reader = _ObservingStore(context.store, context.domain.domain_root)

    def mutate_read_set(view: GovernanceCommitViewV2) -> None:
        assert view.committed_transition is not None
        entries = list(view.committed_transition.batch.read_set.entries)
        selected = entries[0]
        entries[0] = replace(
            selected,
            expected_root=_root("tampered-read-root"),
        )
        read_set = GovernanceAuthorityReadSetV2(
            entries=tuple(sorted(entries, key=lambda item: item.stream_ref.encode()))
        )
        object.__setattr__(view.committed_transition.batch, "read_set", read_set)

    reader.view_mutator = mutate_read_set
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as read_caught:
        rehydrate_risk_state_v2(
            request.to_dict(), domain=context.domain, state_reader=reader
        )
    assert read_caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )

    finality_reader = _ObservingStore(context.store, context.domain.domain_root)
    finality_reader.finality_transition_ids.add(request.transition_id)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as finality_caught:
        rehydrate_risk_state_v2(
            request.to_dict(), domain=context.domain, state_reader=finality_reader
        )
    assert finality_caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )


def test_parent_finality_unavailable_blocks_child_before_atomic_commit() -> None:
    wrapper: _ObservingStore | None = None

    def wrap(store: GovernanceStateStoreV2, domain_root: str) -> GovernanceStateStoreV2:
        nonlocal wrapper
        wrapper = _ObservingStore(store, domain_root)
        return cast(GovernanceStateStoreV2, wrapper)

    context = _context(scope_ref="scope:risk-v2:parent-finality", store_wrapper=wrap)
    assert wrapper is not None
    genesis, genesis_source = _request(context, advance_ref="advance:genesis")
    assert _advance(context, genesis, genesis_source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    child, child_source = _request(
        context,
        advance_ref="advance:child",
        risk_band=RiskBand.HIGH,
        parent=genesis.snapshot,
        current_step=3,
    )
    wrapper.finality_transition_ids.add(genesis.transition_id)
    attempt = _advance(context, child, child_source)[0]
    assert attempt.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert attempt.failure is not None
    assert attempt.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )


def test_v1_v2_risk_and_threshold_semantics_are_differentially_equal() -> None:
    commit_policy = cast(
        CollectiveCommitPolicy,
        _manifest().collective_commit_policy,
    )
    run_ref = "run:risk-v2:differential"
    commit_root = commit_policy_fingerprint(commit_policy, profile=PROFILE)
    v1_state = initialize_risk_assessment_chain(
        commit_policy=commit_policy,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=commit_root,
        protocol_id=PROTOCOL_REF,
        run_id=run_ref,
        target=TARGET,
        epoch=EPOCH,
        issuer_id="issuer:risk-v2",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=1,
        expires_at_step=20,
        provenance="urn:test:risk-v2:differential:chain",
        trace_event_id="trace:risk-v2:differential:chain",
    )
    v1_assessment, v1_next = issue_risk_assessment(
        v1_state,
        assessment_id="assessment:differential",
        risk_band=RiskBand.HIGH,
        risk_input_fingerprints=(INPUT_B, INPUT_A),
        rationale_codes=("governance_risk_classification",),
        assessment_method="declared-risk-matrix-v1",
        commit_policy=commit_policy,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=commit_root,
        protocol_id=PROTOCOL_REF,
        run_id=run_ref,
        target=TARGET,
        epoch=EPOCH,
        issuer_id="issuer:risk-v2",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=20,
        provenance="urn:test:risk-v2:differential",
        trace_event_id="trace:risk-v2:differential",
    )
    v1_threshold = issue_commit_threshold_snapshot(
        v1_assessment,
        chain_state=v1_next,
        threshold_id="threshold:differential",
        commit_policy=commit_policy,
        issuer_id="issuer:risk-v2",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=2,
        provenance="urn:test:risk-v2:differential:threshold",
        trace_event_id="trace:risk-v2:differential:threshold",
    )
    domain_root = _root("risk-v2:differential:domain")
    v2, _ = prepare_risk_state_advance_v2(
        domain_root=domain_root,
        scope_ref="scope:risk-v2:differential",
        manifest=_manifest(commit_policy),
        profile=PROFILE,
        run_ref=run_ref,
        target_ref=TARGET,
        epoch=EPOCH,
        advance_ref="advance:differential",
        current_step=2,
        assessment_ref="assessment:differential",
        risk_band=RiskBand.HIGH,
        risk_input_roots=(INPUT_B, INPUT_A),
        rationale_codes=("governance_risk_classification",),
        assessment_method="declared-risk-matrix-v1",
        issuer_ref="issuer:risk-v2",
        issued_at_step=2,
        expires_at_step=20,
        provenance_ref="urn:test:risk-v2:differential",
        source_trace_roots=(_root("trace:risk-v2:differential"),),
    )
    assessment = v2.snapshot.assessment
    threshold = v2.snapshot.threshold
    assert (
        assessment.assessment_ref,
        assessment.issuer_ref,
        assessment.risk_band,
        assessment.risk_input_roots,
        assessment.rationale_codes,
        assessment.assessment_method,
        assessment.issued_at_step,
        assessment.expires_at_step,
        assessment.window_reset_required,
        assessment.provenance_ref,
        assessment.source_trace_roots,
    ) == (
        v1_assessment.assessment_id,
        v1_assessment.issuer_id,
        v1_assessment.risk_band,
        v1_assessment.risk_input_fingerprints,
        v1_assessment.rationale_codes,
        v1_assessment.assessment_method,
        v1_assessment.issued_at_step,
        v1_assessment.expires_at_step,
        v1_assessment.window_reset_required,
        v1_assessment.provenance,
        (_root(v1_assessment.trace_event_id),),
    )
    assert (
        threshold.risk_band,
        threshold.minimum_positive_evidence,
        threshold.maximum_counterevidence,
        threshold.maximum_counterevidence_ratio_ppm,
        threshold.minimum_support_clusters,
        threshold.minimum_support_ratio_ppm,
        threshold.minimum_source_diversity,
        threshold.minimum_margin,
        threshold.stability_steps,
        threshold.required_challenge_categories,
        threshold.minimum_assurance,
        threshold.publishable_outcomes,
        threshold.executable_outcomes,
    ) == (
        v1_threshold.risk_band,
        v1_threshold.minimum_positive_evidence,
        v1_threshold.maximum_counterevidence,
        v1_threshold.maximum_counterevidence_ratio_ppm,
        v1_threshold.minimum_support_clusters,
        v1_threshold.minimum_support_ratio_ppm,
        v1_threshold.minimum_source_diversity,
        v1_threshold.minimum_margin,
        v1_threshold.stability_steps,
        v1_threshold.required_challenge_categories,
        v1_threshold.minimum_assurance,
        v1_threshold.publishable_outcomes,
        v1_threshold.executable_outcomes,
    )
    assert threshold.to_dict()["extensions"] == {}
